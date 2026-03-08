"""
aws_fetcher.py — Cliente Real de AWS (Patrón Cache-Refresh)

Conecta con las APIs reales de AWS para sincronizar datos:
  1. AWS Pricing API  → Precios On-Demand de instancias EC2
  2. Service Quotas   → Límite de vCPUs de la cuenta

IMPORTANTE:
  - La API de Pricing de AWS solo existe en us-east-1 y ap-south-1.
    El cliente SIEMPRE se conecta a us-east-1 sin importar la región
    de las instancias consultadas.
  - Los datos se cachean en data/aws_prices_quotas.json para que
    el motor Z3 los lea instantáneamente sin llamar a AWS cada vez.

Uso:
    python engine.py sync-aws-data                    # Regiones por defecto
    python engine.py sync-aws-data --regions us-east-1 eu-west-1
"""

import json
import os
import boto3
from typing import List, Dict, Any, Optional

# Directorio de datos
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CACHE_FILE = os.path.join(DATA_DIR, "aws_prices_quotas.json")

# Tipos de instancia comunes a consultar por defecto
DEFAULT_INSTANCE_TYPES = [
    "t3.micro",
    "t3.medium",
    "m5.large",
    "m5.xlarge",
    "c5.2xlarge",
    "r5.2xlarge",
    "p3.8xlarge",
    "p4d.24xlarge",
    "g5.48xlarge",
    "x1e.32xlarge",
]

# Mapeo de código de región AWS → nombre legible para la API de Pricing
# La API de Pricing usa "location" (nombre humano), no el código de región
REGION_DISPLAY_NAMES = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-south-1": "EU (Milan)",
    "eu-south-2": "EU (Spain)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "sa-east-1": "South America (Sao Paulo)",
}

# Código de cuota de AWS para "Running On-Demand Standard instances" (vCPUs)
VCPU_QUOTA_CODE = "L-1216C47A"


def _get_ec2_price(
    pricing_client,
    instance_type: str,
    region_display_name: str,
) -> Optional[float]:
    """
    Obtiene el precio On-Demand por hora de una instancia EC2.

    NOTA: El cliente de pricing SIEMPRE debe estar conectado a us-east-1.
    El parámetro 'location' es el nombre legible de la región (ej: "EU (Ireland)"),
    NO el código de región (ej: "eu-west-1").
    """
    filtros = [
        {"Type": "TERM_MATCH", "Field": "ServiceCode", "Value": "AmazonEC2"},
        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
        {"Type": "TERM_MATCH", "Field": "location", "Value": region_display_name},
        {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
        {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
        {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
        {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
    ]

    try:
        respuesta = pricing_client.get_products(
            ServiceCode="AmazonEC2",
            Filters=filtros,
        )
    except Exception as e:
        print(f"    ⚠️  Error consultando precio de {instance_type}: {e}")
        return None

    if not respuesta.get("PriceList"):
        return None

    # AWS devuelve un JSON anidado (string dentro de dict)
    datos_precio = json.loads(respuesta["PriceList"][0])

    # Navegar el laberinto del JSON para extraer el precio On-Demand
    try:
        terms = datos_precio["terms"]["OnDemand"]
        id_term = list(terms.keys())[0]
        price_dimensions = terms[id_term]["priceDimensions"]
        id_dimension = list(price_dimensions.keys())[0]
        precio_por_hora = float(price_dimensions[id_dimension]["pricePerUnit"]["USD"])
        return precio_por_hora
    except (KeyError, IndexError):
        return None


def _get_instance_vcpus(
    ec2_client,
    instance_type: str,
) -> Optional[int]:
    """Obtiene el número de vCPUs de un tipo de instancia vía DescribeInstanceTypes."""
    try:
        resp = ec2_client.describe_instance_types(InstanceTypes=[instance_type])
        if resp["InstanceTypes"]:
            return resp["InstanceTypes"][0]["VCpuInfo"]["DefaultVCpus"]
    except Exception as e:
        print(f"    ⚠️  Error obteniendo vCPUs de {instance_type}: {e}")
    return None


def _get_vcpu_quota(quotas_client) -> Optional[float]:
    """
    Obtiene la cuota de vCPUs On-Demand Standard de la cuenta.
    Código de cuota: L-1216C47A (Running On-Demand Standard instances).
    """
    try:
        respuesta = quotas_client.get_service_quota(
            ServiceCode="ec2",
            QuotaCode=VCPU_QUOTA_CODE,
        )
        return respuesta["Quota"]["Value"]
    except Exception as e:
        print(f"    ⚠️  Error obteniendo cuota de vCPUs: {e}")
        return None


def sync_aws_data(
    regions: Optional[List[str]] = None,
    instance_types: Optional[List[str]] = None,
    aws_profile: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Conecta con AWS, descarga precios reales y cuotas, y actualiza
    el archivo data/aws_prices_quotas.json (caché local).

    Patrón Cache-Refresh:
      - Se ejecuta una vez con: python engine.py sync-aws-data
      - Los datos quedan cacheados en disco
      - El motor Z3 lee del JSON local (respuesta en milisegundos)

    Args:
        regions: Lista de códigos de región (ej: ["us-east-1", "eu-west-1"])
        instance_types: Tipos de instancia a consultar
        aws_profile: Nombre del perfil de AWS CLI a usar
    """
    if regions is None:
        regions = ["us-east-1"]
    if instance_types is None:
        instance_types = DEFAULT_INSTANCE_TYPES

    print("\n" + "=" * 60)
    print("  🔄 Sincronizando datos reales desde AWS")
    print("=" * 60)

    # Crear sesión con el perfil indicado
    session_kwargs = {}
    if aws_profile and aws_profile != "default":
        session_kwargs["profile_name"] = aws_profile
    session = boto3.Session(**session_kwargs)

    # ── 1. Cliente de Pricing (SIEMPRE us-east-1) ────────────────
    print("\n  [1/3] 💲 Conectando a AWS Pricing API (us-east-1)...")
    pricing_client = session.client("pricing", region_name="us-east-1")

    # ── 2. Obtener precios y vCPUs de cada instancia ─────────────
    print(f"  [2/3] 📊 Consultando precios de {len(instance_types)} tipos de instancia...")

    # Usamos la primera región para obtener metadata de instancias
    primary_region = regions[0]
    ec2_client = session.client("ec2", region_name=primary_region)
    region_display = REGION_DISPLAY_NAMES.get(primary_region, primary_region)

    resources = []
    for itype in instance_types:
        print(f"    → {itype}...", end=" ", flush=True)

        precio = _get_ec2_price(pricing_client, itype, region_display)
        vcpus = _get_instance_vcpus(ec2_client, itype)

        if precio is not None and vcpus is not None:
            resources.append({
                "id": itype,
                "vcpu": vcpus,
                "cost_per_hour": round(precio, 4),
                "max_qty": 10,  # Valor conservador por defecto
            })
            print(f"${precio:.4f}/h, {vcpus} vCPUs ✓")
        else:
            print(f"no disponible en {primary_region} ✗")

    # ── 3. Obtener cuotas por región ─────────────────────────────
    print(f"\n  [3/3] 🔒 Consultando Service Quotas por región...")

    regional_quotas = {}
    global_quota = 0

    for region in regions:
        print(f"    → {region}...", end=" ", flush=True)
        quotas_client = session.client("service-quotas", region_name=region)
        quota = _get_vcpu_quota(quotas_client)

        if quota is not None:
            quota_int = int(quota)
            regional_quotas[region] = quota_int
            global_quota = max(global_quota, quota_int)
            print(f"{quota_int} vCPUs ✓")
        else:
            regional_quotas[region] = 64  # Default seguro de AWS
            print(f"usando default (64 vCPUs)")

    if global_quota == 0:
        global_quota = 64

    # ── Construir y guardar el JSON ──────────────────────────────
    data = {
        "global_vcpu_quota": global_quota,
        "regional_quotas": regional_quotas,
        "resources": resources,
        "_metadata": {
            "source": "AWS Pricing API + Service Quotas API",
            "regions_queried": regions,
            "instance_types_queried": instance_types,
        },
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n  ✅ Datos sincronizados y guardados en data/aws_prices_quotas.json")
    print(f"     → {len(resources)} instancias con precios reales")
    print(f"     → Cuota máxima: {global_quota} vCPUs")
    print(f"     → Regiones: {regions}")
    print("=" * 60)

    return data
