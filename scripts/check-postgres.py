"""Integration checks against the isolated test installation only."""
import os
import sys
import uuid
import psycopg

sys.path.insert(0, '/app')
from app.repositories.postgres_market import PostgresArchive, PostgresGamma
from app.repositories.postgres_state import PostgresRecords, PostgresDocument, PostgresEdge
from app.repositories.archive_repository import ArchiveRepository
from app.repositories.gex_repository import GexRepository

market=os.environ['PR_MARKET_DSN']; state=os.environ['PR_STATE_DSN']
for schema,path,gamma in [('legacy','/market/replay_archive.sqlite','/market/gex_qqq.db'),('modern','/market/purplechart_v2_archive.sqlite','/market/purplechart_v2_archive.sqlite')]:
    pg=PostgresArchive(path,market,schema,os.environ['PR_TICK_URL']); sq=ArchiveRepository(path)
    assert pg.symbols(1)==sq.symbols(1)
    for symbol in pg.symbols(1):
        lo,hi=sq.time_range(symbol); end=min(hi,lo+120)
        assert pg.time_range(symbol)==sq.time_range(symbol)
        for method,args in [('stats',(symbol,lo,end)),('profile',(symbol,lo,end)),('delta_minutes',(symbol,lo,end)),('candle_buckets',(symbol,60,lo,end)),('session_ranges',(symbol,))]:
            a=getattr(pg,method)(*args);b=getattr(sq,method)(*args)
            if isinstance(a,list): a=sorted(a);b=sorted(b)
            assert a==b,(schema,symbol,method)
        rows=pg.trades_after(symbol,lo,50); original=sq.trades_after(symbol,lo,50)
        assert sorted(rows)==sorted((r[0],str(r[1]),*r[2:]) for r in original),(schema,symbol,'Go ticks')
    assert PostgresGamma(market,schema).last_level_before('2099')==GexRepository(gamma).last_level_before('2099')

workspace='integration-'+uuid.uuid4().hex
r=PostgresRecords(state,workspace,'trades');r.append({'pnl':12,'mode':'replay'})
assert r.read_all()==[{'pnl':12,'mode':'replay'}]
assert not PostgresRecords(state,workspace+'other','trades').read_all()
d=PostgresDocument(state,workspace,'checkpoint');d.write({'cursor':1});d.write({'cursor':2});assert d.read()=={'cursor':2}
e=PostgresEdge(state,workspace);key=e.insert_trade({'pnl':12,'entry_tag':'test'});assert e.count()==1 and e.list_trades(1)[0]['id']==key
with psycopg.connect(market,autocommit=True) as c:
    for sql in ['DELETE FROM modern.tape_trades','SELECT * FROM simulation.records']:
        try:c.execute(sql)
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('market reader permissions too broad')
with psycopg.connect(state,autocommit=True) as c:
    try:c.execute('SELECT * FROM modern.tape_trades LIMIT 1')
    except psycopg.errors.InsufficientPrivilege:pass
    else:raise AssertionError('journal writer permissions too broad')

# This DSN is supplied only by the test harness, never to the runtime service.
admin=os.environ['TEST_ADMIN_DSN']
with psycopg.connect(admin,autocommit=True) as c:
    try:
        c.execute("INSERT INTO modern.tape_trades SELECT 'NQ',4102444800,'integration-'||i,'2100-01-01T00:00:00Z',100+i,1,'buy' FROM generate_series(1,5) i")
        pg=PostgresArchive('/unused',market,'modern',os.environ['PR_TICK_URL'])
        rows=pg.trades_after('NQ',4102444799,2)
        assert len(rows)==5,'Go must retain every tick at a shared timestamp'
        assert not pg.trades_after('NQ',4102444800,2)
    finally:
        c.execute("DELETE FROM modern.tape_trades WHERE t=4102444800 AND id LIKE 'integration-%%'")
        c.execute('DELETE FROM simulation.records WHERE workspace=%s',(workspace,))
        c.execute('DELETE FROM simulation.documents WHERE workspace=%s',(workspace,))
print('PASS: Go/PostgreSQL parity, tied ticks, simulation persistence, visitor separation and database role restrictions')
