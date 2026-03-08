# 🛡️ IAM Axiom Verifier

**A Neuro-Symbolic Inference Engine for AWS Security & FinOps**

IAM Axiom Verifier es una herramienta de **auditoría matemática** para entornos AWS. Combina la flexibilidad de los Modelos de Lenguaje Grande (LLMs) para el enrutamiento semántico con el **rigor absoluto** de los solucionadores SMT (Verificación Formal) para evaluar políticas IAM.

En lugar de confiar en expresiones regulares, heurísticas o alucinaciones de IA, este motor traduce el estado de AWS a un sistema de **inecuaciones y lógica booleana**, demostrando matemáticamente los vectores de riesgo.

---

## 🚨 El Problema

- **La IA alucina:** Los LLMs no pueden razonar de forma fiable sobre grafos de permisos complejos o cuotas de servicio. Un error en la auditoría de seguridad es **inaceptable**.

- **Las calculadoras estáticas fallan:** Calcular el "Radio de Explosión" (Blast Radius) financiero de una credencial comprometida no es un simple sumatorio; es un problema de **optimización combinatoria (NP-Hard)** cruzado con restricciones de cuotas de AWS y lógica booleana de IAM.

---

## ✨ La Solución (Características Principales)

Este proyecto implementa una arquitectura **Neuro-Simbólica "2 en 1"**:

### 🔒 Módulo 1: Verificador Formal de Accesos (SAT Solver)

Traduce las políticas de AWS (Allows/Denies explícitos e implícitos) a **teoremas booleanos**. Demuestra si existe algún camino lógico para que un rol acceda a un recurso crítico.

La ecuación que Z3 evalúa:

```
Permiso_Concedido = Hay_Allow AND NOT Hay_Deny_Explicito
```

### 💸 Módulo 2: Optimizador de Radio de Explosión Financiera (Max-SAT / ILP)

Cruza los permisos IAM con la API de precios y los Service Quotas de AWS. Utiliza **Programación Lineal Entera (ILP)** para encontrar la combinación exacta de instancias y regiones que el atacante usaría para infligir el daño económico máximo.

La función objetivo:

```
Maximizar: C = Σ(cost_i × x_i × P_i)
Sujeto a:  Σ(vcpu_i × x_i × P_i) ≤ Q   ∧   0 ≤ x_i ≤ max_qty_i
```

---

## 🧠 Arquitectura (Cómo funciona)

El sistema impone un **límite estricto** entre el razonamiento probabilístico (LLM) y la ejecución determinista (Z3):

```
┌─────────────────────────────────────────────────────────────┐
│                    Pregunta del usuario                     │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Capa 1: Intención (LLM)                                   │
│  → Enrutador Semántico: extrae rol, acción, intención       │
│  → Pydantic valida el JSON estricto (LLMIntent)             │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Capa 2: Fetcher Determinista (AWS / boto3)                 │
│  → Descarga políticas IAM reales del rol                    │
│  → Obtiene Service Quotas y precios públicos                │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Capa 3: Compilación (IAM → SMT)                           │
│  → Parsea JSON de IAM a PolicyStatements tipados            │
│  → Cruza permisos con catálogo de precios                   │
└──────────┬────────────────────────────────────┬─────────────┘
           ▼                                    ▼
┌────────────────────────┐    ┌──────────────────────────────┐
│  Capa 4a: SAT Solver   │    │  Capa 4b: ILP Solver         │
│  Verificación Acceso   │    │  Blast Radius Financiero     │
│  → UNSAT = Imposible   │    │  → SAT = Coste máximo        │
└────────────────────────┘    └──────────────────────────────┘
```

---

## 💻 Ejemplos de Uso

El paquete expone una interfaz natural para el usuario final:

```python
from engine import VerifierEngine

engine = VerifierEngine(aws_profile="produccion")

# CASO 1: Verificación Formal de Acceso
resultado = engine.ask("¿Pueden los desarrolladores junior borrar la base de datos de producción?")
print(resultado.proof)
# > ❌ UNSAT: Matemáticamente demostrado. El rol 'DevTeam-Junior'
# > tiene un Deny explícito en 'rds:DeleteDBInstance'.

# CASO 2: Optimización de Daño Financiero (Blast Radius)
resultado = engine.ask("¿Cuál es el radio de explosión financiero si hackean al equipo de datos?")
print(resultado.proof)
# > ⚠️ SAT (Max-Cost): El daño máximo es de $45,200/día.
# > Vector de ataque óptimo calculado por Z3:
# > Levantar instancias p4d.24xlarge (límite de cuota regional) en us-east-1.
```

---

## 🛠️ Instalación y Ejecución

```bash
# 1. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar la demo (ambos módulos, datos mock locales)
python3 engine.py demo
```

---

## 🔄 Sincronización con AWS Real (Cache-Refresh)

En producción, la herramienta se conecta a las **APIs reales de AWS** para obtener precios y cuotas actualizadas de la cuenta del cliente.

> [!IMPORTANT]
> La API de Pricing de AWS **solo existe en `us-east-1`** y `ap-south-1`.
> El cliente siempre se conecta a `us-east-1` aunque consultes precios de instancias en España (`eu-south-2`) o Japón.

```bash
# Sincronizar precios y cuotas desde AWS (requiere credenciales configuradas)
python3 engine.py sync-aws-data

# Especificar regiones y perfil
python3 engine.py sync-aws-data --regions us-east-1 eu-west-1 --profile produccion
```

Este comando:
1. Conecta con **AWS Pricing API** (`us-east-1`) para obtener precios On-Demand reales
2. Conecta con **AWS Service Quotas API** (por región) para obtener el límite de vCPUs (`L-1216C47A`)
3. Sobrescribe `data/aws_prices_quotas.json` con datos **100% reales**

Después, el motor Z3 lee instantáneamente del JSON local — **determinista y en milisegundos**.

---

## 🔐 Configuración de AWS (Privilegio Mínimo)

Para conectarse a AWS de forma segura, la herramienta usa un **usuario IAM dedicado con permisos de solo lectura**. Nunca uses tu usuario administrador.

### 1. Crear la política de permisos

El archivo [`docs/iam-axiom-readonly-policy.json`](docs/iam-axiom-readonly-policy.json) contiene la política mínima necesaria. Solo permite:
- **`iam:List*` / `iam:Get*`** — Leer políticas IAM (nunca modificar)
- **`pricing:GetProducts`** — Consultar precios públicos de EC2
- **`servicequotas:Get*` / `servicequotas:List*`** — Consultar límites de la cuenta

> [!CAUTION]
> Esta política es **read-only**. La herramienta no puede crear, modificar ni eliminar ningún recurso en tu cuenta AWS.

### 2. Crear el usuario IAM dedicado

```
AWS Console → IAM → Users → Create user
```

1. **Nombre:** `iam-axiom-auditor`
2. **Acceso a consola:** ❌ No (solo acceso programático)
3. **Permisos:** `Attach policies directly` → `Create policy` → pegar el contenido de [`iam-axiom-readonly-policy.json`](docs/iam-axiom-readonly-policy.json)
4. **Crear Access Keys:** Pestaña `Security credentials` → `Create access key` → seleccionar `Command Line Interface (CLI)`

AWS te dará un **Access Key ID** y un **Secret Access Key**.

### 3. Configurar el perfil local

```bash
aws configure --profile axiom-auditor
# AWS te pedirá:
#   AWS Access Key ID:     ********
#   AWS Secret Access Key: ********
#   Default region name:   us-east-1
#   Default output format: json
```

### 4. Usar el perfil en la herramienta

```bash
# Sincronizar con el perfil de mínimos privilegios
python3 engine.py sync-aws-data --profile axiom-auditor --regions us-east-1 eu-west-1
```

Internamente, `boto3` usa ese perfil aislado:

```python
session = boto3.Session(profile_name='axiom-auditor')
pricing_client = session.client('pricing', region_name='us-east-1')
iam_client = session.client('iam')
```

---

## 📂 Estructura del Proyecto

```
iam-axiom-verifier/
├── .env.example                 # Plantilla para API Keys (OpenAI/Anthropic)
├── .gitignore                   # Ignora /venv, __pycache__, .env y cachés locales
├── LICENSE                      # Licencia del proyecto (ej. MIT o Apache 2.0)
├── README.md                    # Documentación principal
├── requirements.txt             # Dependencias estrictas (boto3, z3-solver, pydantic)
├── engine.py                    # Entrypoint: Fachada principal y CLI
│
├── src/                         # 🧠 Código fuente desacoplado
│   ├── __init__.py
│   ├── models.py                # Contratos de Datos (Pydantic v2)
│   ├── aws/                     # Capa 2: Fetcher Determinista
│   │   ├── __init__.py
│   │   ├── fetcher.py           # Cliente real (Pricing + Quotas con boto3)
│   │   └── parser.py            # Parsea políticas IAM a objetos tipados
│   ├── core/                    # Capas 3-4: Inferencia Matemática
│   │   ├── __init__.py
│   │   └── smt_solver.py        # Motores SAT e ILP (Z3)
│   └── llm/                     # Capa 1: IA Probabilística
│       ├── __init__.py
│       └── router.py            # Enrutador Semántico (Traductor LLM)
│
├── data/                        # 💾 Caché local y Mocks para desarrollo
│   ├── policy_devteam.json      
│   ├── policy_dataeng.json      
│   └── aws_prices_quotas.json   
│
└── docs/                        # 📄 Documentación técnica y seguridad
    └── iam-axiom-readonly-policy.json
```

---

## 🔧 Stack Tecnológico

| Componente | Tecnología |
|---|---|
| **Core Lógico** | `z3-solver` (Microsoft Research) |
| **Integración Cloud** | `boto3` (AWS SDK) |
| **Enrutador IA** | OpenAI API / Anthropic API |
| **Contratos de Datos** | `pydantic` v2 |

