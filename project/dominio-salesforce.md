# AgentMind Hub — Dominio: Salesforce CRM

Fuente de verdad sobre el dominio del caso de uso.
Todo el dataset sintético, el corpus RAG, los specs de agentes y los ejemplos
de prueba deben ser coherentes con este documento.

---

## Por qué Salesforce CRM

Salesforce es el CRM enterprise más extendido en consulting (Deloitte es uno de
los mayores SIs de Salesforce del mundo). Sus incidencias tienen tres propiedades
que lo hacen ideal como dominio de AgentMind Hub:

1. **Complejidad real.** Un bug en un Apex trigger puede afectar a miles de
   registros en cascada; un fallo de integración puede bloquear el pipeline de
   ventas de toda una empresa. El RCA no es trivial.
2. **Multicapa.** Configuración (Flows, reglas), código (Apex, LWC), integración
   (APIs, middleware), datos (calidad, duplicados) y permisos (perfiles, PS).
   Cada capa tiene sus herramientas y su forma de investigar.
3. **Trazabilidad de negocio.** Cada incidencia tiene un impacto medible: deals
   bloqueados, casos sin respuesta, emails no enviados, CPQ sin precio. Eso hace
   que Priority (impacto × urgencia) sea no trivial y justifique el LLM en ambiguos.

---

## Taxonomía de incidencias

### Categorías (campo `category` del IncidentState)

| Código | Categoría | Descripción |
|---|---|---|
| `APEX` | Apex / Código | Errores en triggers, clases, tests, batch jobs |
| `FLOW` | Flow / Automation | Flows, Process Builder, Workflow Rules que fallan |
| `INTEG` | Integración | APIs, middleware (MuleSoft, Boomi), sync con ERP/SAP |
| `PERM` | Permisos / Seguridad | Usuarios sin acceso, PS incorrectos, sharing rules |
| `DATA` | Calidad de datos | Duplicados, campos vacíos, corrupción, sync roto |
| `PERF` | Rendimiento | Timeouts, queries lentas, límites de gobernador |
| `CPQ` | CPQ / Precios | Cálculo de precios, configuración de bundles, aprobaciones |
| `REPORT` | Reports / Dashboards | Datos incorrectos, filtros rotos, permisos de carpeta |
| `EMAIL` | Email / Notificaciones | Alertas no enviadas, templates rotos, deliverability |
| `UI` | UI / UX | Errores de página, Lightning bugs, componentes LWC |

### Sistemas afectados (campo `system` del IncidentState)

| Código | Sistema |
|---|---|
| `SALES_CLOUD` | Sales Cloud (Opp, Account, Contact, Lead) |
| `SERVICE_CLOUD` | Service Cloud (Cases, Entitlements, Knowledge) |
| `CPQ` | Salesforce CPQ / Revenue Cloud |
| `MARKETING` | Marketing Cloud / Pardot |
| `INTEGRATION` | Capa de integración (APIs, middleware) |
| `PLATFORM` | Plataforma (Apex, Flows, permisos, datos) |
| `ANALYTICS` | Reports, Dashboards, CRM Analytics |

### Severidades (campo `severity` del IncidentState)

| Nivel | Nombre | Criterio | SLA respuesta | SLA resolución |
|---|---|---|---|---|
| `P1` | Crítico | Sistema caído, todos los usuarios afectados, impacto en revenue | 15 min | 4h |
| `P2` | Alto | Feature crítica rota, muchos usuarios afectados, workaround complejo | 1h | 8h |
| `P3` | Medio | Feature degradada, workaround disponible, usuarios parcialmente afectados | 4h | 24h |
| `P4` | Bajo | Issue menor, cosmético, un usuario o caso aislado | 8h | 72h |

---

## Mapa de objetos Salesforce (relevante para RCA y Solution)

El RCA Agent necesita entender las relaciones entre objetos para trazar el
impacto y la causa raíz. Este es el modelo mínimo que debe conocer:

```
Account ──┬── Contact
          ├── Opportunity ──── Quote (CPQ)
          │                └── OpportunityLineItem
          └── Case ──── Entitlement
                   └── CaseComment

Lead ──── (convertido a) ──── Account + Contact + Opportunity

User ──── Profile ──── PermissionSet
      └── Role ──── (jerarquía de visibilidad)

Apex Trigger ──── SObject (cualquiera de los anteriores)
Flow          ──── SObject / Platform Event
```

**Relaciones de alto impacto en incidencias:**
- Un trigger en `Opportunity` que falla bloquea TODOS los saves de oportunidades.
- Un Flow en `Case` roto puede paralizar el equipo de soporte completo.
- Un fallo de permisos en `Account` puede invisibilizar registros a un equipo entero.
- Un fallo de CPQ en `Quote` bloquea el proceso de oferta → cierre.

---

## Corpus RAG — Qué se indexa en pgvector

El RCA Agent busca en este corpus para fundamentar su análisis causal.
Se indexan tres tipos de documentos:

### 1. Histórico de incidencias resueltas
Cada incidencia resuelta en el pasado, con su causa raíz y solución aplicada.
Son el corazón del RAG: "este error ya lo vimos, la causa fue X, la solución fue Y".

Campos relevantes para el embedding:
- Título + descripción del ticket
- Categoría, sistema, severidad
- Causa raíz identificada
- Solución aplicada
- Objetos Salesforce involucrados
- Error messages exactos (los stacktraces son oro para el retrieval)

### 2. Documentación técnica del org
- Descripción de los Apex triggers más críticos (qué hacen, cuándo se disparan)
- Inventario de Flows activos y sus condiciones de disparo
- Mapa de integraciones: qué sistemas, qué APIs, qué frecuencia, qué campos
- Reglas de asignación y escalado de Cases
- Estructura de perfiles y Permission Sets principales

### 3. Runbooks de resolución
Guías paso a paso para los problemas más frecuentes:
- "Cómo diagnosticar un trigger que falla en bulk"
- "Cómo depurar un Flow con error de tipo de dato"
- "Cómo trazar un fallo de integración por límites de API"
- "Cómo identificar el origen de un problema de permisos"

**Nota de chunking (para S3):** Los stacktraces de Apex no se deben trocear;
van como chunk completo. La documentación técnica se trocea por sección lógica
(un trigger = un chunk). Los runbooks se trocean por paso.

---

## Dataset sintético — Blueprint

El script `scripts/generate_incidents.py` debe generar este mix:

### Volumen y distribución

| Tipo | Nº incidencias | Propósito |
|---|---|---|
| Incidencias resueltas (histórico RAG) | 150 | Corpus de búsqueda del RCA Agent |
| Incidencias de prueba (test set) | 30 | Evaluación end-to-end del pipeline |
| Incidencias ambiguas (edge cases) | 20 | Forzar el LLM en Priority; probar el gate HITL |

**Distribución por severidad (histórico):**
- P1: 10% (15 tickets) — pocos pero críticos, bien documentados
- P2: 25% (37 tickets) — el grueso del trabajo real
- P3: 40% (60 tickets) — los más frecuentes
- P4: 25% (38 tickets) — ruido de fondo

**Distribución por categoría (histórico):**
- APEX: 25% — son los más ricos para RCA
- FLOW: 20%
- INTEG: 20%
- PERM: 10%
- DATA: 10%
- PERF: 5%
- Resto: 10% repartido

### Estructura de cada incidencia (JSON)

```json
{
  "incident_id": "INC-2024-0042",
  "created_at": "2024-03-15T09:23:00Z",
  "title": "Apex trigger OpportunityTrigger falla al actualizar stage a Closed Won",
  "description": "Cuando el comercial cambia la etapa de una oportunidad a 'Closed Won', el sistema devuelve el error 'FIELD_CUSTOM_VALIDATION_EXCEPTION' y no guarda el cambio. Afecta a todo el equipo de ventas de EMEA. Se detectó a las 09:15 CET.",
  "reporter": "john.smith@cliente.com",
  "category": "APEX",
  "system": "SALES_CLOUD",
  "severity": null,
  "confidence": null,
  "priority_score": null,
  "priority_rationale": null,
  "affected_users": 45,
  "affected_objects": ["Opportunity", "OpportunityTrigger"],
  "error_messages": [
    "FIELD_CUSTOM_VALIDATION_EXCEPTION: Revenue recognition date cannot be in the past"
  ],
  "root_cause": null,
  "solution_proposed": null,
  "resolution_notes": "El trigger OpportunityTrigger invocaba una validación de fecha que usaba 'Today()' en lugar de la fecha de cierre del deal. Tras el cambio de zona horaria del servidor en el mantenimiento del sábado, la comparación fallaba para deals cerrados antes de medianoche UTC.",
  "resolved_at": "2024-03-15T13:45:00Z",
  "resolution_time_hours": 4.37,
  "comms_sent": true,
  "comms_approved_by": "maria.gonzalez@deloitte.com"
}
```

**Campos que llegan vacíos (los rellena el pipeline):**
`severity`, `confidence`, `priority_score`, `priority_rationale`, `root_cause`,
`solution_proposed`. Las incidencias del histórico tienen todo relleno; las del
test set solo tienen lo que escribiría un usuario real.

### 10 arquetipos de incidencia (el script genera variaciones de cada uno)

1. **Trigger en Opportunity roto tras deploy** — el clásico. Stacktrace claro, causa en el código.
2. **Flow de onboarding de Case que no dispara** — configuración, condiciones de entrada erróneas.
3. **Integración con SAP que falla por límites de API** (429 / Too Many Requests).
4. **Usuarios del equipo de EMEA sin acceso a cuentas de cliente** — sharing rule incorrecta.
5. **Duplicados masivos en Account tras migración de datos** — deduplication rule desactivada.
6. **Batch job de CPQ timeout por query sin índice** — problema de rendimiento / SOQL.
7. **Precio de bundle CPQ incorrecto para descuentos > 30%** — lógica de pricing rule.
8. **Dashboard de pipeline de ventas con datos del mes pasado** — refresh schedule roto.
9. **Email de bienvenida no se envía al crear Lead desde web** — workflow rule desactivada.
10. **Lightning component de gestión de contratos da error 500** — bug en LWC / Apex controller.

---

## Cómo usa cada agente este dominio

### Intake Agent
- Clasifica el ticket en `category` y `system` usando el vocabulario de las tablas de arriba.
- Detecta si la descripción menciona objetos Salesforce conocidos (Opportunity, Case, Flow...) para reforzar la clasificación.
- Emite `confidence` baja si la descripción es vaga ("algo no funciona en Salesforce").

### Priority Agent
- Reglas deterministas: P1 automático si `affected_users > 100` o si `system = INTEGRATION` con keyword "down". P2 si afecta a Sales Cloud en cierre de trimestre (fechas codificadas).
- LLM en ambiguos: si la descripción menciona impacto en revenue pero los campos no lo dejan claro.
- El campo `affected_users` del JSON es la palanca principal de `impacto`.

### RCA Agent
- Busca en el histórico de incidencias resueltas: "¿hemos visto este error antes?"
- Busca en la documentación técnica: "¿qué hace el trigger/flow mencionado?"
- Busca en runbooks: "¿hay un procedimiento de diagnóstico para esta categoría?"
- Tools: `query_incident_history`, `search_technical_docs`, `search_runbooks`.
- **Read-only siempre.** No modifica nada en Salesforce.

### Solution Agent
- Recibe la causa raíz del RCA y propone el fix concreto.
- El subagente Corrective Developer busca en el código fuente del org (si está indexado) la función/trigger/flow afectado.
- Emite: descripción del fix, archivos a modificar, riesgo estimado, pasos de testing.
- **Propone, no aplica.**

### Comms Agent
- Redacta el email al equipo técnico con: resumen ejecutivo, causa raíz, solución propuesta, próximos pasos, SLA status.
- El template HTML usa los campos del `IncidentState` final.
- El gate HITL muestra el email al aprobador antes de enviar.

---

## Decisiones de dominio (log)

- **2026-07:** Salesforce CRM elegido como dominio único para todo el dataset sintético,
  corpus RAG y casos de prueba. Reemplaza el dominio genérico de "incidencias IT".
- **2026-07:** El script `generate_incidents.py` debe generar 200 incidencias en total
  (150 histórico + 30 test + 20 edge cases), coherentes con la taxonomía de este fichero.
- **2026-07:** Los objetos Salesforce del mapa (Account, Opportunity, Case, etc.) son
  el vocabulario base del Intake Agent para structured output.
- **2026-07:** El corpus RAG (S3) se indexa en tres colecciones pgvector separadas:
  `incident_history`, `technical_docs`, `runbooks`. El RCA decide qué colección consultar.
