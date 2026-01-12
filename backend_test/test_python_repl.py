import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../backend'))

from agents.tools.python_repl import python_repl

async def test_python_repl():
    print("🚀 Testing E2B Python REPL Tool...")
    
    # Simple calculation test
    code = """
import json

# Calculate landed cost for e-bike import
unit_price = 2500  # USD
freight_cost = 150  # USD per unit
mexico_import_tax = 0.20  # 20%
brazil_import_tax = 0.35  # 35%

landed_cost_mexico = unit_price + freight_cost + (unit_price * mexico_import_tax)
landed_cost_brazil = unit_price + freight_cost + (unit_price * brazil_import_tax)

result = {
    "unit_price_usd": unit_price,
    "freight_per_unit": freight_cost,
    "landed_cost_cdmx": landed_cost_mexico,
    "landed_cost_sao_paulo": landed_cost_brazil
}

print(json.dumps(result, indent=2))
"""
    
    try:
        print("▶️ Executing Python code...")
        result = await python_repl.ainvoke({"code": code})
        
        print("\n✅ Result:")
        print(result)
        
        if "landed_cost" in result.lower() or "3150" in result:
            print("\n✅ Python REPL working correctly!")
        else:
            print("\n⚠️ Output doesn't contain expected values")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_python_repl())
