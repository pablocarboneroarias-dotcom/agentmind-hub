# Spec — Priority Agent

**Semana:** S2
**Tipo:** Workflow (reglas deterministas + gate condicional a LLM)
**Patrón:** Rule-based classification con escalado condicional
**Perfil de modelo:** `fast` / `local` (solo en los casos que escalan; el
cálculo determinista no usa modelo)

---

## Qué hace

Calcula la prioridad (P1-P4) de una incidencia ya clasificada por Intake,
combinando dos ejes — **Impacto** y **Urgencia** — en una matriz determinista,
y deriva el **SLA** correspondiente por lookup. No investiga, no diagnostica,
no decide causa raíz: solo prioriza con la información que ya tiene.

## Por qué es workflow, no agente

Dado un `IncidentState` con los campos de Intake rellenos, el camino es
siempre el mismo: calcular impacto → calcular urgencia → mirar la matriz →
mirar el SLA. No hay iteración, no hay elección de herramientas, no hay
decisión sobre "cuántos pasos dar". Los dos puntos donde interviene un LLM
son **gates de escalado**, no razonamiento autónomo — el LLM resuelve una
sub-tarea puntual (interpretar semántica que el regex no captura) y devuelve
el control al workflow determinista.

---

## Inputs (de `IncidentState`, ya rellenados por Intake)

| Campo | Origen | Uso en Priority |
|---|---|---|
| `category` | Intake | Contexto para el matching de impacto |
| `system` | Intake | Contexto para el matching de impacto |
| `business_process` | Intake | Lookup en tabla de urgencia base |
| `business_process_confidence` | Intake | Gate de escalado de urgencia (no reinventa una confianza propia) |
| `urgency_hint` | Intake | Evidencia adicional, no decide por sí sola |
| `title`, texto libre del ticket | Ticket original | Matching de impacto (contenido crítico) + volumen de afectados si viene explícito |

**Importante:** Priority NO recalcula la clasificación de Intake. Si
`business_process` viene vacío o Intake no confía en su propia clasificación,
Priority lo hereda como señal de riesgo — no lo "arregla" por su cuenta.

---

## Cálculo de Impacto (3 niveles: Alto / Medio / Bajo)

1. Matching por reglas contra un diccionario de:
   - Frases de contenido crítico (ej. "no se puede contratar en toda el
     área", "todo el CTI caído", "no se envían contratos a distribuidora").
   - Volumen de afectados si viene explícito en el ticket (>100 o "toda una
     oficina" → Alto; 10-100 → Medio; <10 → Bajo).
2. Cada regla que matchea suma a un **score de cobertura** (0-1): proporción
   de señales del ticket que encuentran match literal o semántico claro en
   el diccionario.
3. **Gate a LLM (perfil `fast`):** si `score_impacto < 0.7`, se delega la
   clasificación de impacto al LLM, que recibe el texto del ticket y el
   diccionario de referencia, y devuelve Alto/Medio/Bajo + su propia
   `confidence`.
4. Si el LLM también da baja confianza (`< 0.5`) → marcar
   `needs_human_review: true` en vez de forzar una clasificación.

## Cálculo de Urgencia (3 niveles: Alta / Media / Baja)

1. Lookup directo en la tabla `business_process → urgencia_base` (vive en
   `docs/dominio-salesforce.md`, ver tabla de referencia abajo).
2. **Gate a LLM (perfil `fast`):** se escala si:
   - `business_process` está vacío (Intake no pudo mapear el ticket a
     ningún valor del enum cerrado — ya no puede llegar aquí un valor
     inventado que "aparente" ser válido, ver nota de enum cerrado arriba), **o**
   - `business_process_confidence` (la confianza que Intake le puso a esa
     clasificación) es menor que `0.8` — umbral más estricto que el `0.6`
     de Intake, porque un error aquí es más costoso.
3. El LLM, si interviene, infiere el proceso de negocio real desde el texto
   libre del ticket y devuelve urgencia + confianza propia.

### Tabla de referencia — `business_process → urgencia_base`

**Fuente de verdad: `dominio-salesforce.md`.** La tabla completa (12
categorías, incluida `CIERRE_OPORTUNIDAD_VENTA`, añadida tras el caso real
`INC-2026-0731`) vive únicamente en ese fichero — no se duplica aquí para
evitar que spec y dato de negocio se desincronicen si alguien actualiza uno
y olvida el otro. El nodo `priority_node` debe leer esa tabla en tiempo de
ejecución, nunca hardcodearla.

**IMPORTANTE — `business_process` es un enum cerrado, no texto libre**
(ver corrección de spec de Intake). Si Intake devuelve un valor fuera de
este enum, la validación de Pydantic falla en origen y el caso se trata
como `business_process` vacío: dispara el gate a LLM en Urgencia igual que
cualquier otro caso sin clasificar. Antes de este fix, el LLM podía
devolver valores fuera de cualquier vocabulario cerrado (se observó
`"SALES_FLOW"` usado así en `INC-2026-0731`, antes de que ese código
existiera formalmente en `dominio-salesforce.md`) y Priority hacía un
lookup fantasma contra una fila que no existía realmente en ninguna tabla
validada — el gate de confianza no lo detectaba porque el problema no era
de confianza baja, era de valor inexistente. Ahora `SALES_FLOW` es un código
válido del enum (proceso comercial / pipeline de ventas, urgencia Media,
ver `dominio-salesforce.md`), así que este caso concreto ya no dispara el
gate — solo lo dispara un valor que siga sin existir en el vocabulario
cerrado.

## Matriz Impacto × Urgencia → Prioridad

| | Urgencia Alta | Urgencia Media | Urgencia Baja |
|---|---|---|---|
| **Impacto Alto** | P1 | P2 | P3 |
| **Impacto Medio** | P2 | P3 | P3 |
| **Impacto Bajo** | P3 | P3 | P4 |

Lookup puro, sin excepciones ni LLM. Si Impacto o Urgencia quedaron en
`needs_human_review`, la matriz no se ejecuta — se detiene antes.

## SLA por Prioridad (lookup determinista)

| Prioridad | SLA respuesta | SLA resolución |
|---|---|---|
| P1 | 15 min | 2h |
| P2 | 30 min | 4h |
| P3 | 2h | 24h |
| P4 | 8h | 48h |

*(Ajustar si Ellevio tiene SLAs contractuales distintos por cliente — de
momento, tabla de referencia genérica.)*

---

## Outputs (escritos en `IncidentState`)

| Campo | Tipo | Descripción |
|---|---|---|
| `impact_level` | `"alto" \| "medio" \| "bajo"` | Nivel de impacto calculado |
| `impact_confidence` | `float` | Confianza (regla o LLM) |
| `urgency_level` | `"alta" \| "media" \| "baja"` | Nivel de urgencia calculado |
| `urgency_confidence` | `float` | Confianza (lookup=1.0 fijo, o confianza del LLM si escaló) |
| `priority` | `"P1" \| "P2" \| "P3" \| "P4"` | Resultado de la matriz |
| `sla_response` | `str` | SLA de respuesta, ej. `"15min"` |
| `sla_resolution` | `str` | SLA de resolución, ej. `"2h"` |
| `needs_human_review` | `bool` | `true` si Impacto o Urgencia no se pudieron determinar con confianza suficiente |
| `priority_reasoning` | `str` | Traza corta de qué reglas/gates se activaron (para auditoría) |

## Señal de enrutado (`route_after_priority`)

```
if needs_human_review:
    → cola de revisión humana (no continúa a RCA)
else:
    → RCA Agent
```

---

## Nota de gobernanza

- **Todo el cálculo es auditable por diseño:** cada campo de salida incluye
  su confianza y `priority_reasoning` documenta qué regla o gate se activó.
  Nada de "caja negra" — un auditor debe poder reconstruir por qué una
  incidencia salió P1 sin re-ejecutar el LLM.
- **Priority no corrige a Intake.** Si `business_process` viene vacío o de
  baja confianza, eso se propaga como riesgo (`needs_human_review`), no se
  "adivina" silenciosamente.
- **El umbral de Urgencia (0.8) es más estricto que el de Impacto (0.7)** de
  forma deliberada: un error de urgencia altera directamente el SLA
  contractual, mientras que un error de impacto tiene más margen de
  corrección aguas abajo.
- **La tabla `business_process → urgencia_base` es dato, no código** — vive
  en `dominio-salesforce.md` para que cambios de negocio no requieran tocar
  el nodo.

---

## Lo que Priority no decide (explícito para evitar scope creep)

| Decisión | Quién la toma |
|---|---|
| Categoría / sistema / proceso de negocio | Intake Agent |
| Causa raíz | RCA Agent |
| Solución propuesta | Solution Agent |
| Comunicación al equipo | Comms Agent + gate HITL |
| SLA contractual específico por cliente (si difiere del genérico) | Fuente de datos externa (futuro: lookup a Salesforce vía MCP, S7) |

---

## Entregable esperado de Claude Code

Un nodo LangGraph (`priority_node`) que:
1. Recibe el `IncidentState` con los campos de Intake rellenos (incluyendo
   `business_process_confidence`).
2. Calcula `impact_level` por reglas, con gate a LLM (perfil `fast`) si
   `score_impacto < 0.7`.
3. Calcula `urgency_level` por lookup en la tabla de `dominio-salesforce.md`,
   con gate a LLM (perfil `fast`) si el proceso está vacío/no existe en tabla
   o `business_process_confidence < 0.8`.
4. Aplica la matriz Impacto × Urgencia → Prioridad (lookup puro).
5. Aplica el lookup de SLA por prioridad.
6. Si Impacto o Urgencia quedaron con confianza insuficiente tras el gate a
   LLM, marca `needs_human_review: true` y NO ejecuta la matriz.
7. Escribe todos los campos de salida en el `IncidentState`, incluyendo
   `priority_reasoning`.
8. Tests unitarios con al menos 4 incidencias sintéticas:
   - Un caso P1 claro por reglas (sin gate a LLM), ej. "todo el CTI caído".
   - Un caso que dispara el gate de impacto (ticket ambiguo, score bajo).
   - Un caso que dispara el gate de urgencia (`business_process` vacío o
     baja confianza de Intake).
   - Un caso que termina en `needs_human_review: true` (ambos gates fallan).
