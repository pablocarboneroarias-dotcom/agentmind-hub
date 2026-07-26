# Spec — Intake Agent

**Semana:** S2
**Tipo:** Workflow
**Patrón:** Single call + structured output (alimenta el routing del grafo)
**Perfil de modelo:** `fast` / `local`

---

## Qué hace

Clasifica una incidencia entrante (categoría, sistema, proceso de negocio,
señal de urgencia) mediante una única llamada a LLM con salida estructurada.
No decide severidad, no decide causa raíz, no decide nada aguas abajo — solo
extrae y estructura lo que el ticket ya contiene o permite inferir.

## Por qué es workflow, no agente

Los pasos son siempre los mismos, en el mismo orden, sin importar el
contenido del ticket: leer → extraer campos → emitir structured output. No
hay elección de herramientas, no hay iteración, no hay decisión de proceso.
Un clasificador con LLM es un workflow igual que lo sería un clasificador
con regex, solo que más capaz interpretando lenguaje natural.

---

## Inputs

- `title`, `description` del ticket (texto libre).
- Metadatos del ticket si vienen disponibles (canal, entorno, cuenta,
  contacto) — se pasan al `IncidentState` pero no todos entran al prompt
  (ver privacidad por diseño).

## Outputs (escritos en `IncidentState`)

| Campo | Tipo | Descripción |
|---|---|---|
| `category` | `str` | Categoría técnica (ej. APEX, INTEG, PLATFORM) |
| `system` | `str` | Sistema afectado |
| `business_process` | `BusinessProcess \| null` | **Enum cerrado** — ver corrección abajo |
| `business_process_confidence` | `float` | Confianza específica de esta clasificación |
| `urgency_hint` | `str` | Evidencia para Priority, NO decisión — Priority no usa este campo como fuente de urgencia, es contexto adicional |
| `confidence` | `float` | Confianza global de la clasificación de Intake |
| `needs_clarification` | `bool` | `true` si `confidence < 0.6` |
| `intake_status` | `"ok" \| "rejected"` | `rejected` si fallan ambos perfiles de modelo (ver nota de fallo de infraestructura) |

---

## CORRECCIÓN (post caso real `INC-2026-0731`) — `business_process` es un enum cerrado

**Motivo del cambio:** en la primera versión del spec, `business_process` era
texto libre. Un caso real mostró que el LLM puede inventar un valor
plausible (ej. `"SALES_FLOW"` usado como si fuera un código válido antes de
existir en ningún vocabulario cerrado) con confianza alta (0.95) que no
existía en ninguna tabla validada. Priority hacía un lookup directo contra
ese valor fantasma y asignaba una urgencia sin que nadie la hubiera
decidido — el gate de confianza no lo detectaba porque el problema no era
confianza baja, era un valor inexistente con confianza alta.

**Fix:** `business_process` se restringe a un `Literal` cerrado en el
schema Pydantic de salida de Intake:

```python
BusinessProcess = Literal[
    "CONTRACTING",           # Contratación / Alta de suministro
    "OWNERSHIP_CHANGE",      # Cambio de titularidad
    "CONTRACT_RENEWAL",      # Renovación de contratos
    "SAP_INTEGRATION",       # Integraciones con distribuidora / SAP
    "CUSTOMER_SERVICE",      # CTI / Atención al cliente (telefonía)
    "COMPLAINTS",            # Reclamaciones / Quejas regulatorias
    "BILLING",                # Facturación / Emisión de facturas
    "COLLECTIONS",            # Gestión de cobros / Impagos
    "METER_READING",          # Lecturas / Telemedida
    "REPORTING",              # Reporting interno / Dashboards
    "GENERAL_INQUIRY",        # Consulta general / Información al cliente
    "SALES_FLOW",             # Proceso comercial / pipeline de ventas (Sales Cloud)
    "CPQ",                     # Configuración de precios y ofertas (CPQ)
    "DATA_INTEGRITY",         # Inconsistencia / corrupción de datos entre sistemas o pantallas
]
```

**Nota de sincronización (actualizada):** `docs/dominio-salesforce.md` es
ahora la **fuente de verdad única** de este vocabulario — código, nombre
descriptivo y urgencia base de cada proceso de negocio viven ahí, no en
este spec. Este `Literal` es solo el reflejo técnico en Pydantic; cualquier
cambio de vocabulario se hace primero en `dominio-salesforce.md` y luego se
replica aquí en el mismo cambio.

*(Histórico: `DATA_INTEGRITY` se añadió tras el caso real `INC-2026-0733` —
un ticket de discrepancia de datos entre pantallas que Intake solo pudo
encajar en `GENERAL_INQUIRY` con confianza límite (0.80, justo en el borde
del umbral de gate de Priority), ocultando una urgencia real Alta detrás de
una etiqueta de urgencia Baja. Confirma un patrón: la taxonomía inicial
cubría bien procesos de cara al cliente, pero no síntomas técnicos
transversales de integridad de datos entre sistemas — frecuentes en
integraciones reales, según validación de negocio.)*

Si el LLM no puede mapear el ticket a ninguno de estos valores, debe
devolver `null` — nunca inventar uno. Un `business_process` nulo ya dispara
`needs_clarification` (vía `confidence` baja) o, si llega hasta Priority,
dispara el gate de urgencia a LLM allí. La validación de Pydantic actúa como
defensa en profundidad: si pese a las instrucciones el modelo devuelve un
string fuera del enum, la deserialización falla y el caso se trata como
vacío, nunca como un lookup válido.

---

## Seguridad y privacidad

- **Anti prompt-injection:** el system prompt instruye explícitamente
  ignorar cualquier instrucción embebida en el texto del ticket.
- **Datos mínimos necesarios:** `contact_name`, `reporter_email`,
  `account_name` se pasan al `IncidentState` pero no se incluyen en el
  prompt del LLM salvo que sean estrictamente necesarios para la
  clasificación. Privacidad por diseño.

## Observabilidad

Latencia, tokens, coste y modelo usado los captura LangSmith
automáticamente. No se añaden al `IncidentState` para no contaminarlo con
metadatos de infraestructura.

## Nota sobre fallo de infraestructura (post caso real)

Se observó un caso donde **ambos perfiles de modelo (`local` y `fast`)
fallaron por completo** — no fue un problema de ambigüedad del ticket, fue
indisponibilidad del modelo. El comportamiento actual marca
`intake_status: "rejected"` y `needs_clarification: true`, pero **no
distingue este caso de una clasificación genuinamente ambigua** en el
trace, y el campo `urgency_hint` puede quedar con un valor por defecto
engañoso (ej. `"low"`) que no refleja ninguna evaluación real.

**Pendiente de resolver (no bloqueante para S2, anotar para revisión):**
1. El trace debe diferenciar explícitamente "fallo de modelo" de "baja
   confianza de clasificación" — son causas raíz distintas y requieren
   respuesta distinta.
2. Ante fallo total de ambos perfiles, los campos que dependen del LLM
   (`urgency_hint` incluido) deben quedar en `null`/`"unknown"`, nunca con
   un default que sugiera calma o baja prioridad — un ticket sin clasificar
   no es lo mismo que un ticket de baja urgencia, y una cola de revisión
   humana que ordene por urgencia no debe poder confundir ambos casos.

---

## Señal de enrutado (`route_after_intake`)

```
if confidence < 0.6 or intake_status == "rejected":
    → needs_clarification = true → cola de revisión / HITL (S6)
else:
    → Priority Agent
```

---

## Lo que Intake no decide (explícito para evitar scope creep)

| Decisión | Quién la toma |
|---|---|
| Severidad P1/P2/P3/P4 | Priority Agent |
| Causa raíz | RCA Agent |
| Solución propuesta | Solution Agent |
| Comunicación al equipo | Comms Agent + gate HITL |
| Escritura en Salesforce | Integración autorizada (S7, vía MCP) |

---

## Entregable esperado de Claude Code

Un nodo LangGraph (`intake_node`) que:
1. Recibe el `IncidentState` con los campos del ticket rellenos.
2. Llama a LiteLLM con perfil `local` (fallback a `fast` si falla) y
   structured output (Pydantic schema con `business_process` como enum
   cerrado, ver corrección arriba).
3. Aplica el vocabulario de `dominio-salesforce.md` para validar los
   valores.
4. Escribe los campos de salida en el `IncidentState`.
5. Ante fallo de ambos perfiles, marca `intake_status: "rejected"` sin
   inventar valores por defecto engañosos en campos dependientes del LLM.
6. Tests unitarios con al menos 4 incidencias sintéticas: un APEX claro, un
   INTEG claro, un ticket vago con `needs_clarification: true`, y un caso de
   `business_process` fuera del enum conocido (para confirmar que se
   rechaza y no se inventa).
