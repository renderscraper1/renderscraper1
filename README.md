# Sistema listo para Render + Supabase/Postgres

Este proyecto ya no guarda `BloqueJSON.db`.

## Qué hace
- lee VTEX por categorías y páginas
- valida EAN con checksum matemático
- guarda solo EAN válidos
- mantiene una tabla actual por EAN
- guarda historial solo cuando el precio, lista o stock cambia
- corre en Render como cron job
- expone un health check mínimo

## Variables de entorno
- `DATABASE_URL`: conexión PostgreSQL de Supabase
- `PORT`: puerto del health check
- `SCRAPER_MAX_CONCURRENCY`: concurrencia HTTP

## Despliegue en Render
- usar `render.yaml`
- agregar `DATABASE_URL` como variable secreta
- crear cada `config_*.py` del lado del repo

## Tablas
El sistema crea automáticamente:
- `current_products`
- `price_history`

## Idea de uso
- Render cron job ejecuta `python app.py run`
- el scraper procesa solo lo necesario
- Supabase/Postgres conserva únicamente datos livianos y útiles
