"""Client-bound conversation/proposal operations on the existing private BoardStore."""
import json
import re
import uuid
from .adapters import Failure, private_json
from .core import PROJECT, Principal, now, version


class ClientControls:
    """Server-owned client -> existing obligation. Never accepts browser routing fields."""
    def __init__(self, path=None, records=None):
        self.path, self.records = path, records

    def resolve(self, reference):
        from .board_store import client_reference
        rows = self.records if self.records is not None else private_json(self.path).get('clients', []) if self.path else []
        if not isinstance(rows, list) or len(rows) > 1000:
            raise Failure('client_controls_invalid',503)
        found=[]
        for row in rows:
            if not isinstance(row,dict) or set(row) != {'clientRef','continuationRef'}:
                raise Failure('client_controls_invalid',503)
            ref=client_reference(row['clientRef'])
            if ref is None:raise Failure('client_controls_invalid',503)
            if not isinstance(row['continuationRef'],str) or not re.fullmatch(r'qitem-[A-Za-z0-9_-]{1,160}',row['continuationRef']):
                raise Failure('client_controls_invalid',503)
            if ref == reference:found.append(row['continuationRef'])
        if len(found)!=1:raise Failure('client_conversation_control_unavailable',503)
        return found[0]


class ClientConversations:
    @staticmethod
    def client_key(reference):
        return 'crm:'+reference['entity']+':'+reference['externalId']

    def client_permission(self, principal, reference, write=False, edit=False):
        if (not reference or self.client_key(reference) not in principal.conversation_clients
                or not principal.board_read or PROJECT not in principal.projects
                or (write and not principal.board_respond) or (edit and not principal.proposal_edit)):
            raise Failure('client_conversation_forbidden',403)

    def context_allowed(self, principal, task_id, db=None):
        if db is None:
            with self.db() as connection:return self.context_allowed(principal,task_id,connection)
        row=db.execute('SELECT c.entity,c.external_id FROM client_conversations x JOIN task_clients c ON c.task_id=x.task_id WHERE x.task_id=?',(task_id,)).fetchone()
        return bool(row and self.client_key({'entity':row['entity'],'externalId':row['external_id']}) in principal.conversation_clients)

    def open_client_conversation(self, principal, reference, body, validate_client, controls, resolve_obligation):
        from .board_store import fields, text, client_reference, DESTINATIONS
        reference=client_reference(reference)
        self.client_permission(principal,reference,write=True)
        fields(body,('requestId','text'))
        payload={'clientRef':reference,'text':text(body.get('text'),4000)}
        operation='client-conversation:'+self.client_key(reference)
        with self.db() as db:
            existing=self.replay(db,principal,operation,body.get('requestId'),payload)
        if existing:return self.detail(principal,existing)
        validate_client(reference)  # Never create from an unverified or forbidden CRM object.
        obligation=controls.resolve(reference)
        destination=resolve_obligation(obligation,DESTINATIONS['clients'])
        if destination!=DESTINATIONS['clients']:raise Failure('client_agent_forbidden',409)
        with self.db() as db:
            task_id=self.replay(db,principal,operation,body.get('requestId'),payload)
            if not task_id:
                row=db.execute('SELECT x.task_id,e.native_ref,e.destination FROM client_conversations x JOIN task_clients c ON c.task_id=x.task_id JOIN task_execution e ON e.task_id=x.task_id WHERE c.entity=? AND c.external_id=?',(reference['entity'],reference['externalId'])).fetchone()
                if row:
                    if row['native_ref']!=obligation or row['destination']!=destination:
                        raise Failure('client_conversation_binding_changed',409)
                    task_id=row['task_id']
                else:
                    task_id='task_'+uuid.uuid4().hex
                    db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',(task_id,PROJECT,'Обсуждение предложения','Клиентский контекст; не разрешение отправки или бронирования.','clients',principal.subject,now()))
                    db.execute('INSERT INTO task_clients VALUES(?,?,?)',(task_id,reference['entity'],reference['externalId']))
                    db.execute('INSERT INTO task_execution(task_id,native_ref,destination) VALUES(?,?,?)',(task_id,obligation,destination))
                    db.execute('INSERT INTO client_conversations VALUES(?)',(task_id,))
                self.insert_message(db,task_id,principal,'comment',payload['text'],None)
                self.remember(db,principal,operation,body['requestId'],payload,task_id)
        return self.detail(principal,task_id)

    def proposal(self, db, task_id, revision=None):
        sql='SELECT * FROM proposal_revisions WHERE task_id=?'
        args=[task_id]
        if revision is not None:sql+=' AND revision=?';args.append(revision)
        row=db.execute(sql+' ORDER BY revision DESC LIMIT 1',args).fetchone()
        return {**dict(row),'clientRef':self.client_ref(db,task_id)} if row else None

    def insert_proposal(self, db, task_id, principal, body, source_message):
        from .board_store import fields, text
        fields(body,('baseRevision','title','body'))
        current=self.proposal(db,task_id)
        base=current['revision'] if current else 0
        if type(body.get('baseRevision')) is not int or body['baseRevision']!=base:
            raise Failure('proposal_revision_conflict',409)
        title,content=text(body.get('title'),240),text(body.get('body'),8000)
        db.execute('INSERT INTO proposal_revisions VALUES(?,?,?,?,?,?,?,?,?)',
                   (task_id,base+1,base,title,content,principal.subject,principal.role,source_message,now()))
        return base+1

    def save_proposal(self, principal, task_id, body):
        from .board_store import fields
        fields(body,('requestId','baseRevision','title','body'))
        payload={k:v for k,v in body.items() if k!='requestId'}
        with self.db() as db:
            self.task(db,principal,task_id,write=True)
            self.client_permission(principal,self.client_ref(db,task_id),write=True,edit=True)
            if not db.execute('SELECT 1 FROM client_conversations WHERE task_id=?',(task_id,)).fetchone():
                raise Failure('client_conversation_required',409)
            existing=self.replay(db,principal,'proposal:'+task_id,body.get('requestId'),payload)
            if existing:return self.proposal(db,task_id,int(existing))
            current=self.proposal(db,task_id)
            if not current:raise Failure('agent_proposal_required',409)
            revision=self.insert_proposal(db,task_id,principal,payload,current['source_message'])
            self.remember(db,principal,'proposal:'+task_id,body['requestId'],payload,str(revision))
            return self.proposal(db,task_id,revision)

    def agent_reply(self, delivery_id, session, body, transport):
        """Managed-seat-only caller verifies identity; HTTP never exposes this operation."""
        from .board_store import fields, text
        fields(body,('requestId','text','proposal'))
        content=text(body.get('text'),4000)
        actor=Principal(session,'agent',(PROJECT,))
        operation='agent-reply:'+delivery_id
        with self.db() as db:
            row=db.execute('SELECT o.*,m.task_id FROM outbox o JOIN messages m ON m.id=o.message_id JOIN client_conversations x ON x.task_id=m.task_id WHERE o.id=?',(delivery_id,)).fetchone()
            if not row or row['destination']!=session or row['state']!='delivered' or not row['received_at']:
                raise Failure('agent_context_forbidden',403)
            existing=self.replay(db,actor,operation,body.get('requestId'),body)
            if existing:return {'messageId':existing,'replayed':True}
            pinned=dict(row)
        # Exact native obligation ownership remains required, including on the second round.
        transport.validate_destination(pinned)
        with self.db() as db:
            row=db.execute('SELECT o.*,m.task_id FROM outbox o JOIN messages m ON m.id=o.message_id WHERE o.id=?',(delivery_id,)).fetchone()
            existing=self.replay(db,actor,operation,body.get('requestId'),body)
            if existing:return {'messageId':existing,'replayed':True}
            if db.execute("SELECT 1 FROM messages WHERE reply_to=? AND kind='agent_reply'",(row['message_id'],)).fetchone():
                raise Failure('agent_reply_already_saved',409)
            message_id='message_'+uuid.uuid4().hex
            db.execute('INSERT INTO messages(id,task_id,author,author_role,kind,body,reply_to,created_at) VALUES(?,?,?,?,?,?,?,?)',
                       (message_id,row['task_id'],session,'agent','agent_reply',content,row['message_id'],now()))
            if 'proposal' in body:self.insert_proposal(db,row['task_id'],actor,body['proposal'],message_id)
            self.remember(db,actor,operation,body['requestId'],body,message_id)
            return {'messageId':message_id,'replayed':False}


CONVERSATION_SCHEMA=[
'CREATE TABLE IF NOT EXISTS client_conversations(task_id TEXT PRIMARY KEY REFERENCES tasks(id))',
'''CREATE TABLE IF NOT EXISTS proposal_revisions(task_id TEXT NOT NULL REFERENCES tasks(id),revision INTEGER NOT NULL,
base_revision INTEGER NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,author TEXT NOT NULL,author_role TEXT NOT NULL,
source_message TEXT NOT NULL REFERENCES messages(id),created_at TEXT NOT NULL,PRIMARY KEY(task_id,revision))''']
