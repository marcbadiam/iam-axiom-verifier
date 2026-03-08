# Motor FinOps-SMT

Este repositorio implementa un sistema para calcular el máximo daño financiero (coste por hora/día) que una entidad (usuario/rol) puede infligir en AWS si sus credenciales son comprometidas. Utiliza un LLM con decodificación estructurada para mapear la hipótesis en lenguaje natural y un motor SMT (Z3) para ejecutar optimización combinatoria.

## Arquitectura de Componentes
1. **Parseador Determinista del Entorno**: Extrae políticas IAM y precios de catálogos locales.
2. **Traductor de Hipótesis (LLM)**: Mapea consultas naturales sobre atacantes a parámetros validados rigurosamente por `pydantic`.
3. **Motor de Optimización Formal (Z3 Solver)**: Toma las salidas de ambos módulos y calcula el vector de ataque más destructivo (satisfaciendo restricciones Booleanas e integrales de programación lineal).

## Instalación y Ejecución

```bash
# 1. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar el orquestador
python auditar_riesgo.py "Calcula el riesgo del perfil DevTeam en la región us-east-1"
```

## Estructura de Archivos
- `auditar_riesgo.py`: Orquestador principal.
- `smt_solver.py`: Definición exhaustiva de funciones objetivo Z3 `(\sum_{i=1}^{n} c_i \cdot x_i \cdot P_i)` y restricciones `(\sum_{i=1}^{n} v_i \cdot x_i \cdot P_i \le Q)`.
- `llm_translator.py`: Llamada simulada a OpenAI garantizando un parseo semántico por Contratos con Pydantic.
- `parser.py`: Lógica de extracción en el entorno determinista.
- `models.py`: Estructuras de Pydantic.
- `data/`: Insumos simulados para la evaluación.
