import argparse
import os
import pathlib
import asyncio
from dotenv import load_dotenv

load_dotenv()
from scraper import discover_configs, run_store

BASE_DIR = pathlib.Path(__file__).parent.resolve()

def parse_args():
    parser = argparse.ArgumentParser(description='Ejecución de Scrapers Autónomos')
    # Eliminamos la obligación de poner "run" o "serve".
    parser.add_argument('--only', nargs='*', help='Lista de store_slug a ejecutar')
    return parser.parse_args()

async def _run_all(only=None):
    configs = discover_configs(BASE_DIR)
    if only:
        only = {x.strip().lower() for x in only}
        configs = [c for c in configs if c[0].lower() in only]
    
    if not configs:
        print('⚠️ No se encontraron archivos config_*.py para ejecutar', flush=True)
        return 1

    for store_slug, module_name in configs:
        print(f'\n=== PROCESANDO: {store_slug.upper()} ===', flush=True)
        try:
            await run_store(store_slug, module_name)
        except Exception as e:
            # Si una plataforma se cae, esto captura el error y salta a la siguiente
            # sin detener el proceso completo. ¡Tu robot es ahora inmortal!
            print(f"❌ Error fatal procesando {store_slug}: {e}", flush=True)
            print("⏩ Saltando a la siguiente plataforma...", flush=True)
            continue 
    
    print('\n🎉 CICLO COMPLETO FINALIZADO 🎉', flush=True)
    return 0

def main():
    args = parse_args()
    raise SystemExit(asyncio.run(_run_all(args.only)))

if __name__ == '__main__':
    main()
