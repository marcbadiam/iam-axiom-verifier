import z3
from typing import List, Dict, Any
from models import LLMHypothesis, ResourceData

def optimize_damage(hypothesis: LLMHypothesis, resources: List[ResourceData], global_quota: int, roles_info: Dict[str, Any]):
    print(f"[*] Inicializando motor SMT (Z3 Solver)...")
    
    solver = z3.Optimize()
    
    # Variables de decisión: x_i (cantidad a instanciar de recurso i)
    x_vars = {}
    
    # Variables acumuladoras para total costo y vCPUs
    total_cost_cents = z3.IntVal(0)
    total_vcpu = z3.IntVal(0)
    
    for res in resources:
        # x_i en el dominio de los Enteros: x_i >= 0
        xi = z3.Int(f"x_{res.id.replace('.','_')}")
        x_vars[res.id] = xi
        solver.add(xi >= 0)
        
        # P_i: Booleano calculado a partir de IAM policies (1 si allowed, 0 si no)
        Pi = 1 if res.allowed else 0
        
        # Multiplicamos el costo (USD) por 10000 y trabajamos en enteros (Céntimos)
        cost_in_cents = int(res.cost_per_hour * 10000)
        
        # Objetivo: C = sum(ci * xi * Pi)
        total_cost_cents += (cost_in_cents * xi * Pi)
        
        # Cuotas: sum(vi * xi * Pi) <= Q
        total_vcpu += (res.vcpu_cost * xi * Pi)
        
    # Restricción: Límite de Cuotas de AWS
    solver.add(total_vcpu <= global_quota)
    
    # Restricciones Booleanas Mutuamente Excluyentes (Roles)
    # (RA or RB) and not (RA and RB)
    R_A = z3.Bool('R_A')
    R_B = z3.Bool('R_B')
    solver.add(z3.And(z3.Or(R_A, R_B), z3.Not(z3.And(R_A, R_B))))
    
    # Función Objetivo: Maximizar el daño financiero total
    print("[*] Inyectando función objetivo de maximización en el sistema...")
    solver.maximize(total_cost_cents)
    
    print("[*] Calculando y satisfaciendo restricciones (solver.check)...")
    if solver.check() == z3.sat:
        model = solver.model()
        max_cost_val = model.eval(total_cost_cents)
        
        # Convertir de vuelta a flotante (USD)
        max_cost_per_hour = max_cost_val.as_long() / 10000.0 if z3.is_int_value(max_cost_val) else 0.0
        
        # Extraer vector óptimo de variables x_i
        attack_vector = []
        for res in resources:
            qty = model.eval(x_vars[res.id]).as_long()
            if qty > 0 and res.allowed:
                attack_vector.append(f"{qty} máquinas {res.id}")
                
        return {
            "status": "sat",
            "max_damage_per_hour": max_cost_per_hour,
            "attack_vector": attack_vector
        }
    else:
        return {"status": "unsat", "max_damage_per_hour": 0.0, "attack_vector": []}
