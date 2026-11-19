[English](../README.md) | [Español](README.es.md)

# {{PROJECT_NAME}}

{{STACK_BADGES}}

## Descripción del Proyecto

**{{PROJECT_NAME}}** — {{ONE_SENTENCE_PROJECT_PITCH}}

Principios operativos del sistema:
1. **Contratos Estrictos:** Esquemas explícitos de entrada/salida entre ingesta, lógica de dominio y adaptadores.
2. **Ejecución Reproducible:** Entorno aislado y puerta única de verificación (`make verify`).
3. **Trazabilidad:** Límites modulares claros y evidencia verificada en cada etapa.

## Estructura del Proyecto

```text
{{PROJECT_NAME}}/
├── .agents/                # Reglas activas, hooks y skills del stack seleccionado
├── docs/                   # Arquitectura, Manual de Usuario y ADRs
├── {{PRIMARY_CODE_DIR}}    # Código fuente principal
├── Makefile                # Interfaz universal (make help)
└── README.md               # Visión general y guía rápida (English)
```

## Despliegue y Ejecución Rápida

```bash
make setup
make dev
make verify
```

## Documentación

| Documento | Enlace | Propósito Principal |
| :--- | :--- | :--- |
| **Manual de Usuario** | [User Guide (EN)](USER_GUIDE.md) | Instalación, variables de entorno, perfiles y resolución de problemas |
| **Arquitectura del Sistema** | [Architecture (EN)](ARCHITECTURE.md) | Diagramas de flujo, límites de módulos y contratos internos |
{{BENCHMARKS_DOC_ROW_DOCS}}| **Decisiones de Arquitectura** | [ADRs](adr/README.md) | Registro histórico de decisiones técnicas clave |
