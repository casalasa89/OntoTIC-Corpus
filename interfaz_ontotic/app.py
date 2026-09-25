"""Interfaz local OntoTIC: actores, evidencia y perfiles reproducibles."""
from __future__ import annotations
from datetime import date
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlparse,parse_qs

from seed import BASE,DB,CAPS,build_database,add_dyads
from framework_core import load_lexicon,norm,document_capability,CODE_TO_CORE

LEXICON=BASE/'sources'/'Diccionario_Semantico_OntoTIC_LDA_V613.xlsx'
_,FORMS=load_lexicon(LEXICON)
STATIC=BASE/'static'
MAX_BODY=600_000
ROLES={'Knowledge generator','Technology developer','Product developer','Disseminator','Financier','Producer','Commercializer','Intermediary','Sin clasificar'}

def connect():
    cx=sqlite3.connect(DB)
    cx.row_factory=sqlite3.Row
    cx.execute('PRAGMA foreign_keys=ON')
    return cx

def get_profile(cx,actor_id):
    actor=cx.execute('SELECT * FROM actors WHERE id=?',(actor_id,)).fetchone()
    if actor is None:return None
    base=cx.execute('SELECT * FROM baseline WHERE actor_id=?',(actor_id,)).fetchone()
    raw=json.loads(base['raw_json']) if base else [0.0]*4
    original=json.loads(base['adjusted_json']) if base else [0.0]*4
    nbase=base['signaled_docs'] if base else 0
    rows=cx.execute('SELECT * FROM documents WHERE actor_id=? ORDER BY id DESC',(actor_id,)).fetchall()
    current=[r for r in rows if r['analytical_status']=='Señal nueva incluida en perfil' and r['signal_json']]
    vectors=[json.loads(r['signal_json']) for r in current]
    n=nbase+len(vectors)
    prior=json.loads(cx.execute("SELECT value FROM metadata WHERE key='prior'").fetchone()[0])
    adjusted=[]
    if n:
        blended=[(raw[i]*nbase+sum(v[i] for v in vectors))/n for i in range(4)]
        lam=n/(n+10)
        adjusted=[lam*blended[i]+(1-lam)*prior[i] for i in range(4)]
        total=sum(adjusted);adjusted=[x/total for x in adjusted]
    evidence=[]
    for r in current[:15]:
        evidence.append({'id':r['id'],'title':r['title'],'date':r['publication_date'],
                         'source':r['source_name'],'url':r['url'],'signals':json.loads(r['signal_json']),
                         'terms':json.loads(r['evidence_json'] or '{}')})
    return {'actor':{'id':actor['id'],'name':actor['name'],'role':actor['role'],'origin':actor['origin']},
            'baseline':{'lda_documents':base['lda_docs'] if base else 0,'signaled_documents':nbase,'scores':original},
            'current':{'scores':adjusted,'capabilities':CAPS,'dominant':CAPS[max(range(4),key=lambda i:adjusted[i])] if n else None,
                       'new_signaled_documents':len(vectors),'all_registered_documents':len(rows),
                       'status':'Perfil base ampliado con señales nuevas' if vectors else ('Perfil publicado, sin señales nuevas' if nbase else 'Evidencia insuficiente')},
            'evidence':evidence}

def recommendations(cx,actor_id,limit=10):
    selected=cx.execute('SELECT id,name FROM actors WHERE id=?',(actor_id,)).fetchone()
    if selected is None:return None
    rows=cx.execute('''SELECT d.*,a.name AS name_a,a.role AS role_a,b.name AS name_b,b.role AS role_b
         FROM dyads d JOIN actors a ON a.id=d.actor_a JOIN actors b ON b.id=d.actor_b
         WHERE (d.actor_a=? OR d.actor_b=?) AND d.potential IS NOT NULL
         ORDER BY d.potential DESC LIMIT ?''',(actor_id,actor_id,limit)).fetchall()
    mine=cx.execute('SELECT adjusted_json FROM baseline WHERE actor_id=?',(actor_id,)).fetchone()
    x=json.loads(mine[0]) if mine else None
    output=[]
    for r in rows:
        partner_id=r['actor_b'] if r['actor_a']==actor_id else r['actor_a']
        partner_name=r['name_b'] if r['actor_a']==actor_id else r['name_a']
        partner_role=r['role_b'] if r['actor_a']==actor_id else r['role_a']
        other=cx.execute('SELECT adjusted_json FROM baseline WHERE actor_id=?',(partner_id,)).fetchone()
        y=json.loads(other[0]) if other else None
        differences=[]
        if x and y:
            gaps=sorted(((y[i]-x[i],CAPS[i]) for i in range(4)),reverse=True)
            differences=[{'capability':cap,'advantage':round(delta,4)} for delta,cap in gaps if delta>=.015][:2]
        output.append({'actor_id':partner_id,'name':partner_name,'role':partner_role,'potential':r['potential'],
                       'reliability':r['reliability'],'priority':r['priority'],'rank':r['structural_rank'],
                       'partner_relative_advantages':differences})
    return {'actor':selected['name'],'recommendations':output,'model':'Díadas congeladas del artículo; hipótesis de ajuste funcional, no colaboraciones observadas'}

class Handler(BaseHTTPRequestHandler):
    def send_json(self,value,status=200):
        payload=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)

    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/actors':
            with connect() as cx:
                items=[dict(r) for r in cx.execute('SELECT id,name,role,origin FROM actors ORDER BY name')]
            return self.send_json({'actors':items,'count':len(items)})
        if path.endswith('/recommendations') and path.startswith('/api/actors/'):
            try:actor_id=int(path.split('/')[3])
            except (ValueError,IndexError):return self.send_json({'error':'Actor inválido'},400)
            with connect() as cx:result=recommendations(cx,actor_id)
            return self.send_json(result if result else {'error':'Actor no encontrado'},200 if result else 404)
        if path=='/api/network':
            with connect() as cx:
                rows=cx.execute('''SELECT d.actor_a,d.actor_b,d.potential,a.name AS a,b.name AS b,a.role AS role_a,b.role AS role_b
                     FROM dyads d JOIN actors a ON a.id=d.actor_a JOIN actors b ON b.id=d.actor_b
                     WHERE d.potential IS NOT NULL ORDER BY d.potential DESC LIMIT 30''').fetchall()
            return self.send_json({'edges':[dict(r) for r in rows],'total_nodes':43,'total_evaluable_edges':741,
                                   'view':'Las 30 puntuaciones superiores del corte publicado; sin convenios observados'})
        if path.startswith('/api/actors/'):
            try:actor_id=int(path.rsplit('/',1)[1])
            except ValueError:return self.send_json({'error':'Actor inválido'},400)
            with connect() as cx:result=get_profile(cx,actor_id)
            return self.send_json(result if result else {'error':'Actor no encontrado'},200 if result else 404)
        if path=='/api/documents':
            q=parse_qs(urlparse(self.path).query)
            try:actor_id=int(q.get('actor_id',['0'])[0])
            except ValueError:return self.send_json({'error':'Actor inválido'},400)
            with connect() as cx:
                docs=[dict(r) for r in cx.execute('''SELECT id,title,publication_year,publication_date,source_name,url,
                      analytical_status,created_at FROM documents WHERE actor_id=? ORDER BY id DESC LIMIT 80''',(actor_id,))]
            return self.send_json({'documents':docs})
        if path in ('/','/index.html','/app.js','/style.css','/network.png','/network.gexf'):
            name='index.html' if path=='/' else path.removeprefix('/')
            content=(STATIC/name).read_bytes()
            mime={'index.html':'text/html','app.js':'application/javascript','style.css':'text/css','network.png':'image/png','network.gexf':'application/gexf+xml'}[name]
            self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8')
            self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
            return
        self.send_json({'error':'Ruta no encontrada'},404)

    def do_POST(self):
        size=int(self.headers.get('Content-Length','0'))
        if size<1 or size>MAX_BODY:return self.send_json({'error':'Tamaño inválido o texto demasiado largo'},413)
        try:data=json.loads(self.rfile.read(size))
        except (ValueError,UnicodeDecodeError):return self.send_json({'error':'JSON inválido'},400)
        path=urlparse(self.path).path
        if path=='/api/actors':
            name=' '.join(str(data.get('name','')).split()).upper()
            role=str(data.get('role','Sin clasificar'))
            if len(name)<3 or len(name)>120 or role not in ROLES:return self.send_json({'error':'Nombre o rol inválido'},400)
            try:
                with connect() as cx:
                    result=cx.execute('INSERT INTO actors(name,role,origin) VALUES(?,?,?)',(name,role,'incorporado en interfaz'))
                    actor_id=result.lastrowid
            except sqlite3.IntegrityError:return self.send_json({'error':'El actor ya existe'},409)
            return self.send_json({'id':actor_id,'name':name},201)
        if path=='/api/documents':
            try:actor_id=int(data.get('actor_id'))
            except (TypeError,ValueError):return self.send_json({'error':'Seleccione un actor'},400)
            title=' '.join(str(data.get('title','')).split());body=str(data.get('text','')).strip()
            source=str(data.get('source','')).strip();url=str(data.get('url','')).strip();date_text=str(data.get('date','')).strip()
            if not (8<=len(title)<=400 and 3<=len(source)<=250 and 200<=len(body)<=500_000):
                return self.send_json({'error':'Indique título, fuente y texto de al menos 200 caracteres'},400)
            try:
                publication=date.fromisoformat(date_text)
                parsed=urlparse(url)
                if parsed.scheme not in ('http','https') or not parsed.netloc:raise ValueError
            except ValueError:return self.send_json({'error':'Fecha ISO o URL inválida'},400)
            with connect() as cx:
                if not cx.execute('SELECT 1 FROM actors WHERE id=?',(actor_id,)).fetchone():return self.send_json({'error':'Actor no encontrado'},404)
                if cx.execute('SELECT 1 FROM documents WHERE actor_id=? AND url=? AND title=?',(actor_id,url,title)).fetchone():
                    return self.send_json({'error':'Documento duplicado para este actor'},409)
                cutoff=date.fromisoformat(cx.execute("SELECT value FROM metadata WHERE key='study_cutoff'").fetchone()[0])
                in_window=date(2010,1,1)<=publication<=cutoff
                if in_window:
                    _,dist,terms,total=document_capability(norm(title+' '+body),FORMS)
                    included=total>0
                    status='Señal nueva incluida en perfil' if included else 'Sin coincidencia semántica; no influye en perfil'
                else:
                    included=False;dist=None;terms={};status='Fuera del corte 2010-01-01 a 2026-08-31'
                cur=cx.execute('''INSERT INTO documents(actor_id,title,publication_year,publication_date,source_name,url,
                        text_body,extracted,analytical_status,signal_json,evidence_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                        (actor_id,title,publication.year,date_text,source,url,body,1,status,
                         json.dumps([dist[c] for c in CAPS]) if included else None,
                         json.dumps({k:v for k,v in terms.items() if k in CODE_TO_CORE},ensure_ascii=False)))
                doc_id=cur.lastrowid
            return self.send_json({'id':doc_id,'status':status,'profile_updated':included},201)
        self.send_json({'error':'Ruta no encontrada'},404)

    def log_message(self,fmt,*args):print(fmt%args,file=sys.stderr)

def main():
    if not DB.exists():build_database()
    else:
        with connect() as cx:
            if not cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dyads'").fetchone():add_dyads(cx)
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'OntoTIC disponible en http://127.0.0.1:{args.port}',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
