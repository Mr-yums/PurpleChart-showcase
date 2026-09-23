"""Import only allowlisted, sanitized market columns. Atomic and restart-safe."""
import csv
import hashlib
import io
import os
import sqlite3
from pathlib import Path
import psycopg

root = Path('/market')
with psycopg.connect(os.environ['IMPORT_DSN'], autocommit=True) as target:
    target.execute('SELECT pg_advisory_lock(12002026)')
    for schema, filename, gamma in [
        ('legacy','replay_archive.sqlite','gex_qqq.db'),
        ('modern','purplechart_v2_archive.sqlite','purplechart_v2_archive.sqlite'),
    ]:
        digest = hashlib.file_digest((root / filename).open('rb'), 'sha256').hexdigest()
        gamma_digest = hashlib.file_digest((root / gamma).open('rb'), 'sha256').hexdigest()
        fingerprint = digest + ':' + gamma_digest
        old = target.execute('SELECT sha256 FROM public.market_imports WHERE source=%s',(schema,)).fetchone()
        if old:
            if old[0] != fingerprint:
                raise SystemExit('Different market archive: use a separate Docker project/volume; existing data preserved')
            print(schema, 'already imported', flush=True)
            continue
        source = sqlite3.connect(f'file:{root / filename}?mode=ro',uri=True)
        print('Importing',schema,flush=True)
        with target.transaction():
            target.execute(f'CREATE TABLE {schema}.tape_trades (symbol text NOT NULL,t double precision NOT NULL,id text NOT NULL,timestamp text NOT NULL,price double precision NOT NULL,volume double precision NOT NULL,side text NOT NULL)')
            count=0
            with target.cursor().copy(f'COPY {schema}.tape_trades FROM STDIN WITH (FORMAT CSV)') as copy:
                cursor=source.execute('SELECT symbol,t,CAST(id AS TEXT),timestamp,price,volume,COALESCE(side,\'unknown\') FROM tape_trades ORDER BY symbol,t')
                while rows:=cursor.fetchmany(50000):
                    buffer=io.StringIO();csv.writer(buffer).writerows(rows);copy.write(buffer.getvalue());count+=len(rows)
                    if count % 1000000 == 0:print(schema,count,flush=True)
            target.execute(f'CREATE INDEX ON {schema}.tape_trades(symbol,t)')
            target.execute(f'CREATE TABLE {schema}.replay_symbols AS SELECT DISTINCT symbol FROM {schema}.tape_trades')
            target.execute(f'CREATE TABLE {schema}.gex(ts text,spot double precision,netGamma double precision,callWall double precision,putWall double precision,inflection double precision)')
            with sqlite3.connect(f'file:{root / gamma}?mode=ro',uri=True) as g:
                with target.cursor().copy(f'COPY {schema}.gex FROM STDIN') as copy:
                    for row in g.execute('SELECT ts,spot,netGamma,callWall,putWall,inflection FROM gex'):copy.write_row(row)
            target.execute(f'CREATE INDEX ON {schema}.gex(ts)')
            target.execute('INSERT INTO public.market_imports VALUES (%s,%s,%s)',(schema,fingerprint,count))
            target.execute(f'ANALYZE {schema}.tape_trades')
        source.close()
        print(schema,'ready',count,flush=True)
