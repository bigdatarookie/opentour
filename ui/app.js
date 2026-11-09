'use strict';

const $ = (id) => document.getElementById(id);
const state = { token: '', session: 0, view: 'tasks', board: null, etag: null, boardBusy: false,
  clients: null, clientRequest: 0, offset: 0, nextOffset: null, modal: null, modalRequest: 0,
  trigger: null, poll: null, debounce: null, campaigns: null, campaignRequest: 0,
  boardAccess: null, appTasks: [], appBusy: false, drafts: new Map() };
const roles = {developer:'Разработка',devops:'Инфраструктура','qa-code':'Проверка кода','qa-system':'Проверка системы',
  engineer:'Данные',creative:'Креатив',designer:'Дизайн',operator:'Оператор',lead:'Координация'};
const columnLabels = {planned:'Запланировано',in_progress:'В работе',needs_human:'Требуется человек',review:'На проверке',done:'Выполнено',unknown:'Неизвестно'};

function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = text;
  return el;
}
function button(text, action, className='secondary-button') {
  const el = node('button', className, text); el.type = 'button'; el.addEventListener('click', action); return el;
}
function announce(text) { $('announcement').textContent = text; }
function timeLabel() { return new Date().toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'}); }
function errorText(error) {
  const code = error.code || '';
  if (error.status === 401) return 'Доступ не подтверждён. Проверьте ключ доступа OpenTour.';
  if (error.status === 403) return 'У этого доступа нет разрешения на просмотр проекта.';
  if (code === 'crm_read_credential_not_configured' || code === 'source_access_unavailable') return 'CRM пока недоступна. Подключение требует проверки.';
  if (error.status === 404) return 'Запись больше не доступна в текущем проекте.';
  return 'Не удалось получить данные. Проверьте подключение и попробуйте ещё раз.';
}
async function api(path, options={}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const headers = {Authorization: `Bearer ${state.token}`};
    if (options.etag) headers['If-None-Match'] = options.etag;
    if (options.body) headers['Content-Type']='application/json';
    const response = await fetch(path, {method:options.body ? 'POST' : 'GET', body:options.body ? JSON.stringify(options.body) : undefined, headers, cache:'no-store', credentials:'omit', signal:controller.signal});
    if (response.status === 304) return {unchanged:true};
    const data = await response.json();
    if (!response.ok) {
      const error = new Error('read_failed'); error.code = data.error; error.status = response.status; throw error;
    }
    return {data, etag:response.headers.get('ETag')};
  } finally { clearTimeout(timeout); }
}

function stateBox(title, description, retry, symbol='○') {
  const box = node('div','state-box');
  box.append(node('span','state-symbol',symbol),node('h3','',title),node('p','',description));
  if (retry) box.append(button('Попробовать ещё раз',retry));
  return box;
}
function showNotice(id, text, retry) {
  const el = $(id); el.replaceChildren(node('span','',text));
  if (retry) el.append(button('Повторить',retry));
  el.hidden = false;
}
function loadingBoard() {
  const skeleton = node('div','loading-columns');
  for (let i=0;i<5;i++) skeleton.append(node('div','skeleton'));
  $('board').replaceChildren(skeleton); $('board').setAttribute('aria-busy','true');
}
function resetSession(message='') {
  state.session++; state.token=''; state.board=null; state.etag=null; state.clients=null;
  state.clientRequest++; state.modalRequest++; state.boardBusy=false; state.modal=null;
  state.campaignRequest++;state.campaigns=null;
  state.boardAccess=null;state.appTasks=[];state.appBusy=false;state.drafts.clear();$('app-tasks').hidden=true;$('app-task-list').replaceChildren();
  state.trigger=null;state.offset=0;state.nextOffset=null;
  clearInterval(state.poll); clearTimeout(state.debounce);
  if ($('detail-dialog').open) $('detail-dialog').close();
  $('board').replaceChildren(); $('client-list').replaceChildren(); $('detail-body').replaceChildren();
  $('campaign-list').replaceChildren();
  $('detail-title').textContent='Подробности';$('client-search').value='';$('client-kind').value='all';$('client-channel').value='any';
  $('work-filter').value='all';$('work-total').textContent='—';$('nav-work-count').textContent='—';$('client-total').textContent='—';
  $('workspace').hidden=true; $('connect-panel').hidden=false; $('disconnect').hidden=true;
  $('synthetic-banner').hidden=true; $('connect-status').textContent=message;
  $('access-token').value=''; $('access-token').focus();
}

$('connect-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  state.token=$('access-token').value.trim();
  const session=++state.session; $('connect-button').disabled=true; $('connect-status').textContent='Проверяем доступ…';
  try {
    await api('/api/capabilities').then(({data}) => {
      if (session !== state.session) return;
      state.boardAccess=data.boardConversations || null;
      $('access-mode').textContent=state.boardAccess?.respond ? 'Ответы в задачах' : 'Только чтение';
      $('synthetic-banner').hidden=data.dataMode !== 'synthetic';
      $('connect-panel').hidden=true; $('workspace').hidden=false; $('disconnect').hidden=false;
      $('access-token').value=''; $('connect-status').textContent='';
      showView(state.view); loadBoard();
      clearInterval(state.poll);
      state.poll=setInterval(() => { if (!document.hidden && state.token) loadBoard(true); },15000);
    });
  } catch(error) {
    if (session === state.session) { state.token=''; $('connect-status').textContent=errorText(error); }
  } finally { $('connect-button').disabled=false; }
});
$('disconnect').addEventListener('click', () => resetSession());

function showView(view) {
  state.view=view;
  for (const el of document.querySelectorAll('[data-view]')) {
    const active=el.dataset.view === view; el.classList.toggle('active',active);
    if (active) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current');
  }
  $('tasks-view').hidden=view !== 'tasks'; $('clients-view').hidden=view !== 'clients';$('campaigns-view').hidden=view !== 'campaigns';
  $('page-title').textContent=({tasks:'Работа команды',clients:'Клиенты',campaigns:'Кампании'})[view];
  $('page-eyebrow').textContent=({tasks:'ОБЩАЯ ДОСКА',clients:'КЛИЕНТСКАЯ БАЗА',campaigns:'ЛОКАЛЬНЫЙ ПРЕДПРОСМОТР'})[view];
  $('page-description').textContent=({tasks:'Текущий план, результаты и следующие шаги.',clients:'Физические лица и организации. Данные из вашей CRM.',campaigns:'Один пакет, все материалы и условия — без отправки.'})[view];
  if (state.token && view === 'clients' && !state.clients) loadClients();
  if (state.token && view === 'campaigns' && !state.campaigns) loadCampaigns();
}
for (const el of document.querySelectorAll('[data-view]')) el.addEventListener('click', () => showView(el.dataset.view));
document.querySelector('.brand').addEventListener('click',(event) => {event.preventDefault();showView('tasks');});
$('refresh').addEventListener('click', () => state.view === 'tasks' ? loadBoard() : state.view === 'clients' ? loadClients() : loadCampaigns());
$('work-filter').addEventListener('change', () => renderBoard());

function ownerLabel(owner) { return roles[owner?.role] || (owner?.kind === 'human_request' ? 'Требуется человек' : 'Команда'); }
function restoreCardFocus(id) {
  for (const el of document.querySelectorAll('[data-object-id]')) if (el.dataset.objectId === id) {el.focus({preventScroll:true});return;}
}
function renderBoard() {
  if (!state.board) return;
  const active=document.activeElement?.dataset?.objectId;
  const filter=$('work-filter').value;
  const items=state.board.items;
  const columns=items.length ? state.board.columns.filter(col => (col.id !== 'unknown' || items.some(item => item.column === 'unknown')) && (filter === 'all' || filter === col.id)) : [];
  const fragment=document.createDocumentFragment();
  for (const col of columns) {
    const section=node('section','column'); section.dataset.column=col.id; section.setAttribute('aria-label',col.label);
    const cards=items.filter(item => item.column === col.id);
    const heading=node('h3','column-heading',col.label); heading.append(node('span','column-count',cards.length)); section.append(heading);
    if (!cards.length) section.append(node('div','column-empty','Работ пока нет'));
    for (const item of cards) {
      const card=button('',() => openDetails('work',item.id,card),'task-card'); card.dataset.objectId=item.id;
      card.append(node('span','task-kind','Работа команды'),node('h3','',item.title),node('p','card-result',item.lastResult || 'Результат пока не зафиксирован'));
      if (item.blockers?.length) card.append(node('span','blocker','Ожидание · '+(item.blockers[0].requestedAction || 'Нужен следующий шаг')));
      const label=ownerLabel(item.owners?.[0]);
      const bottom=node('div','card-bottom'); bottom.append(node('span','avatar',label.slice(0,2).toUpperCase()),node('span','',label),node('span','card-open','↗'));
      card.append(bottom); section.append(card);
    }
    fragment.append(section);
  }
  if (!items.length) fragment.append(stateBox('Пока нет задач','Нативная доска не вернула работ для этого проекта.'));
  if (!columns.length && items.length) fragment.append(stateBox('Нет задач на этом этапе','Выберите другой этап или вернитесь ко всей доске.'));
  $('board').replaceChildren(fragment); $('board').classList.toggle('has-unknown',columns.length>5);
  $('board').setAttribute('aria-busy','false'); $('work-total').textContent=items.length; $('nav-work-count').textContent=items.length;
  if (active && !$('detail-dialog').open) restoreCardFocus(active);
}

async function loadBoard(quiet=false) {
  if (state.boardAccess?.read) loadAppTasks();
  if (!state.token || state.boardBusy) return;
  state.boardBusy=true; const session=state.session;
  if (!state.board) loadingBoard();
  try {
    const result=await api('/api/board',{etag:state.etag});
    if (session !== state.session) return;
    $('board-notice').hidden=true; $('board-updated').textContent='Обновлено в '+timeLabel();
    let reloadingDetail=false;
    if (!result.unchanged) {
      const previous=state.board;
      const data=result.data;
      if (previous?.cursor?.epoch === data.cursor?.epoch && data.cursor.sequence < previous.cursor.sequence) return;
      state.board=data; state.etag=result.etag;
      if (!previous || previous.version !== data.version) {
        renderBoard();
        if (state.modal?.kind === 'work') {
          const changed=data.items.find(item => item.id === state.modal.id);
          if (!changed) renderDetailError('Задача больше не доступна в текущем проекте.');
          else if (changed.version !== state.modal.version) {reloadingDetail=true;loadDetail();}
        }
        if (!quiet) announce('Доска обновлена. '+data.items.length+' задач.');
      }
      if (data.queueWindowComplete === false) showNotice('board-notice','Показана часть нативной истории. Завершение работ по ней не подтверждается.');
    }
    if (!reloadingDetail && state.modal?.kind === 'work') state.modal.observationRefresh?.();
  } catch(error) {
    if (session !== state.session) return;
    if (error.status === 401 || error.status === 403) {resetSession(errorText(error));return;}
    $('board-updated').textContent='Обновление недоступно';
    if (state.board) showNotice('board-notice',errorText(error)+' Показаны последние полученные данные.',() => loadBoard());
    else { $('board').replaceChildren(stateBox('Доска недоступна',errorText(error),() => loadBoard(),'↻')); $('board').setAttribute('aria-busy','false'); }
  } finally { if (session === state.session) state.boardBusy=false; }
}

function clientParams() {
  const query=new URLSearchParams({kind:$('client-kind').value,limit:'12',offset:String(state.offset)});
  const text=$('client-search').value.trim(); if (text) query.set('q',text);
  const channel=$('client-channel').value;
  if (channel === 'email' || channel === 'none') query.set('hasEmail',String(channel === 'email'));
  if (channel === 'phone' || channel === 'none') query.set('hasPhone',String(channel === 'phone'));
  return query;
}
function clientName(item) { return item.displayName || (item.kind === 'organization' ? 'Название не указано' : 'Имя не указано'); }
function fixtureLabels(labels) {
  const row=node('div','fixture-labels');for (const label of labels) row.append(node('span','',label));return row;
}
async function loadCampaigns() {
  if (!state.token) return;
  const request=++state.campaignRequest,session=state.session;
  $('campaign-list').setAttribute('aria-busy','true');$('campaign-list').replaceChildren(node('div','skeleton'));
  try {
    const {data}=await api('/api/campaigns');
    if (session !== state.session || request !== state.campaignRequest) return;
    if (data.mode !== 'FIXTURE') throw new Error('unsupported_campaign_mode');
    state.campaigns=data;
    const content=document.createDocumentFragment();
    for (const item of data.items) {
      if (item.mode !== 'FIXTURE') throw new Error('unsupported_campaign_mode');
      const card=button('',() => openDetails('campaign',item.id,card),'campaign-card');card.dataset.objectId=item.id;
      card.append(node('span','task-kind','EMAIL · ЛОКАЛЬНЫЙ ПАКЕТ r01'),node('h2','',item.title),fixtureLabels(item.labels));
      card.append(node('p','','Аудитория не выбрана · число получателей недоступно'),node('span','source-link','Открыть предпросмотр →'));content.append(card);
    }
    if (!data.items.length) content.append(stateBox('Локальных пакетов нет','Сервис рассылок не подключён. Это не результат проверки провайдера.'));
    $('campaign-list').replaceChildren(content);
  } catch(error) {
    if (session !== state.session || request !== state.campaignRequest) return;
    if (error.status === 401 || error.status === 403) {resetSession(errorText(error));return;}
    state.campaigns=null;$('campaign-list').replaceChildren(stateBox('Пакет недоступен','Локальные материалы не удалось проверить. Данные сервиса рассылок не запрашивались.',() => loadCampaigns(),'↻'));
  } finally {if (session === state.session && request === state.campaignRequest) $('campaign-list').setAttribute('aria-busy','false');}
}
function renderClients() {
  const data=state.clients;
  const fragment=document.createDocumentFragment();
  if (!data.items.length) {
    const box=stateBox('Клиенты не найдены','Попробуйте другой запрос или измените фильтры.');
    box.append(button('Сбросить фильтры',() => { $('client-search').value='';$('client-kind').value='all';$('client-channel').value='any';state.offset=0;loadClients(); }));fragment.append(box);
  } else {
    const header=node('div','client-row client-header'); header.append(node('span','','КЛИЕНТ'),node('span','','EMAIL'),node('span','','ТЕЛЕФОН'),node('span','',''));header.setAttribute('aria-hidden','true');fragment.append(header);
    for (const item of data.items) {
      const row=button('',() => openDetails('client',item.id,row),'client-row');row.dataset.objectId=item.id;
      const name=node('div','client-name'); const title=node('div');title.append(node('strong','',clientName(item)),node('small','',item.kind === 'organization' ? 'Организация' : 'Физическое лицо'));
      name.append(node('span','avatar',item.kind === 'organization' ? 'О' : clientName(item).slice(0,1)),title);
      row.append(name,node('span','client-contact',item.email || 'Email не указан'),node('span','client-contact',item.phone || 'Телефон не указан'),node('span','row-arrow','↗'));fragment.append(row);
    }
  }
  $('client-list').replaceChildren(fragment);$('client-list').setAttribute('aria-busy','false');$('client-total').textContent=data.total;
  $('page-range').textContent=data.total ? `${state.offset+1}–${state.offset+data.items.length} из ${data.total}` : '0 записей';
  $('previous-page').disabled=state.offset === 0;$('next-page').disabled=data.nextOffset === null;state.nextOffset=data.nextOffset;
}
async function loadClients() {
  if (!state.token) return;
  const request=++state.clientRequest,session=state.session;
  $('client-list').setAttribute('aria-busy','true');$('client-total').textContent='—';$('page-range').textContent='Загружаем…';
  $('previous-page').disabled=true;$('next-page').disabled=true;
  const loading=node('div');for(let i=0;i<3;i++) loading.append(node('div','skeleton loading-client'));$('client-list').replaceChildren(loading);
  $('clients-notice').hidden=true;
  try {
    const {data}=await api('/api/clients?'+clientParams());
    if (request !== state.clientRequest || session !== state.session) return;
    state.clients=data;renderClients();announce('Клиентская база обновлена. '+data.total+' записей.');
  } catch(error) {
    if (request !== state.clientRequest || session !== state.session) return;
    if (error.status === 401 || error.status === 403) {resetSession(errorText(error));return;}
    state.clients=null; $('client-list').replaceChildren(stateBox('CRM недоступна',errorText(error),() => loadClients(),'↻'));
    $('client-list').setAttribute('aria-busy','false');$('page-range').textContent='Данные не получены';
  }
}
$('client-filters').addEventListener('submit',event => {event.preventDefault();clearTimeout(state.debounce);state.offset=0;loadClients();});
$('client-search').addEventListener('input',() => {clearTimeout(state.debounce);state.clientRequest++;state.offset=0;state.debounce=setTimeout(loadClients,300);});
for (const id of ['client-kind','client-channel']) $(id).addEventListener('change',() => {clearTimeout(state.debounce);state.offset=0;loadClients();});
$('previous-page').addEventListener('click',() => {state.offset=Math.max(0,state.offset-12);loadClients();});
$('next-page').addEventListener('click',() => {if(state.nextOffset !== null){state.offset=state.nextOffset;loadClients();}});

function detailSection(title,text) {const section=node('section','detail-section');section.append(node('h3','',title),node('p','',text || 'Пока не указано'));return section;}
function metadata(items) {
  const list=node('dl','details-meta'); for (const [title,text] of items) {list.append(node('dt','',title),node('dd','',text || 'Не указано'));}return list;
}
const nativeStateLabels = {pending:'Ожидает', 'in-progress':'В работе', blocked:'Ожидает действия',
  done:'Закрыто в источнике', failed:'Ошибка в источнике', denied:'Отклонено в источнике',
  canceled:'Отменено в источнике', 'handed-off':'Передано в источнике'};
function nativeObservationPanel(item) {
  const previousScroll=$('detail-body').scrollTop;let firstLoad=true;
  const panel=node('section','native-observation detail-section');panel.setAttribute('aria-label','Нативные наблюдения');
  panel.append(node('h3','','Нативные наблюдения'),node('p','detail-note','Только чтение источника. Личность менеджера, принятие решения и продолжение работы не подтверждены.'));
  const all=[...new Set((item.sourceRefs || []).filter(ref => ref.system === 'openrig' && ref.type === 'qitem' && /^[A-Za-z0-9_-]{1,160}$/.test(ref.id)).map(ref => ref.id))];
  const ids=all.slice(0,20),modal=state.modal;
  modal.observationRefresh=null;
  if (!ids.length) {
    modal.originalId=null;panel.dataset.state='no-source';
    panel.append(node('p','','В текущем окне нет доступного исходного поручения для чтения наблюдений. Это не подтверждает отсутствие решений в истории.'));
    return panel;
  }
  modal.originalId=ids.includes(modal.originalId) ? modal.originalId : ids[0];
  const label=node('label','observation-label','Исходное поручение'),select=node('select','observation-select');
  for (const [index,id] of ids.entries()) {const option=node('option','',`${index+1}. ${id}`);option.value=id;select.append(option);}
  select.value=modal.originalId;label.append(select);
  const controls=node('div','observation-controls'),status=node('p','observation-status');status.setAttribute('role','status');
  const result=node('div','observation-result'),reload=button('Обновить наблюдения',() => refresh());
  controls.append(label,reload);panel.append(controls,status,result);
  if (all.length>ids.length) panel.append(node('p','detail-note','Показаны первые 20 ссылок текущего окна. Полная история не загружена.'));
  let request=0,pendingOriginal=null;
  const valid=(sequence,session,original) => sequence === request && session === state.session && state.modal === modal && modal.originalId === original && panel.isConnected;
  async function refresh() {
    const original=modal.originalId;
    if (!panel.isConnected || state.modal !== modal || pendingOriginal === original) return;
    const sequence=++request,session=state.session;pendingOriginal=original;
    const scrollAtStart=$('detail-body').scrollTop;
    reload.setAttribute('aria-disabled','true');result.setAttribute('aria-busy','true');status.textContent='Читаем наблюдения…';panel.dataset.state='loading';
    try {
      const {data}=await api('/api/board/'+encodeURIComponent(item.id)+'/native-decisions/'+encodeURIComponent(original));
      if (!valid(sequence,session,original)) return;
      if (data.project !== item.project || data.mission !== item.mission || data.slice !== item.slice || data.originalTaskId !== original || data.source !== 'native_read_observation' || !['observed','unconfirmed'].includes(data.status) || !Array.isArray(data.observations) || !Array.isArray(data.linkedReplies) || ['humanIdentityVerified','decisionAccepted','ownerActionObserved','executionEnabled','retryAllowed'].some(key => data[key] !== false)) throw new Error('observation_contract_invalid');
      const content=node('div');
      content.append(metadata([['Исходное поручение',nativeStateLabels[data.originalState] || 'Состояние не подтверждено'],['Связанный запрос',data.currentAsk ? nativeStateLabels[data.currentAsk.state] || 'Состояние не подтверждено' : 'В этом чтении не наблюдался']]));
      if (data.status === 'unconfirmed') content.append(node('p','observation-empty','В этом чтении записи аудита и связанные возвраты ответа не наблюдались. Результат не подтверждён.'));
      const events=node('ul','observation-events');
      for (const event of data.observations.slice(0,40)) {
        const name=event.verb === 'answer' ? 'Запись аудита ответа' : 'Запись аудита изменения ожидания';
        events.append(node('li','',`${name}: ${nativeStateLabels[event.beforeState] || 'Неизвестно'} → ${nativeStateLabels[event.afterState] || 'Неизвестно'}`));
      }
      for (const reply of data.linkedReplies.slice(0,20)) events.append(node('li','','Связанный возврат ответа наблюдался в источнике. Содержание и принятие решения не подтверждены.'));
      if (events.children.length) content.append(events);
      const incomplete=[data.queueWindowComplete,data.auditWindowComplete,data.replyWindowComplete].some(value => value !== true);
      content.append(node('p','detail-note',incomplete ? 'Окно наблюдений неполное. По нему нельзя подтвердить отсутствие других записей или завершение работы.' : 'Проверено ограниченное текущее окно. Исторические запросы вне текущей связи не ищутся.'));
      const refs=node('details','detail-provenance');refs.append(node('summary','','Связь наблюдений с источником'),node('p','',`Исходное поручение: ${original}`));
      if (data.currentAsk) refs.append(node('p','',`Текущий запрос: ${data.currentAsk.taskId}`));
      for (const event of data.observations.slice(0,40)) refs.append(node('p','',`Аудит: ${event.actionId} · поручение: ${event.targetTaskId}`));
      for (const reply of data.linkedReplies.slice(0,20)) refs.append(node('p','',`Запрос: ${reply.askTaskId} · возврат: ${reply.replyTaskId}`));
      content.append(refs);result.replaceChildren(content);
      if (firstLoad && $('detail-body').scrollTop === scrollAtStart) $('detail-body').scrollTop=previousScroll;
      firstLoad=false;status.textContent='Наблюдения прочитаны. Это не подтверждение действия человека.';panel.dataset.state=data.status;
    } catch(error) {
      if (!valid(sequence,session,original)) return;
      if (error.status === 401 || error.status === 403) {resetSession(errorText(error));return;}
      result.replaceChildren(node('p','observation-error','Наблюдения недоступны. Отсутствие записей не подтверждено; можно повторить чтение.'));
      status.textContent='Ошибка чтения наблюдений';panel.dataset.state='error';
    } finally {if (sequence === request) pendingOriginal=null;if (valid(sequence,session,original)) {reload.setAttribute('aria-disabled','false');result.setAttribute('aria-busy','false');}}
  }
  select.addEventListener('change',() => {modal.originalId=select.value;result.replaceChildren();refresh();});
  modal.observationRefresh=refresh;queueMicrotask(() => {if (panel.isConnected && state.modal === modal) refresh();});
  return panel;
}
function renderDetailError(text) {$('detail-body').replaceChildren(stateBox('Не удалось открыть',text,() => loadDetail(),'↻'));}
function renderDetail(kind,item) {
  const scroll=$('detail-body').scrollTop;
  const focused=document.activeElement;
  const observationFocus=focused?.matches('.observation-select') ? '.observation-select' : focused?.matches('.observation-controls button') ? '.observation-controls button' : null;
  if (kind === 'app') {renderAppTask(item);return;}
  $('detail-title').textContent=kind === 'work' || kind === 'campaign' ? item.title : clientName(item);
  $('detail-eyebrow').textContent=kind === 'work' ? 'РАБОТА КОМАНДЫ · OPENRIG' : kind === 'campaign' ? 'КАМПАНИЯ · FIXTURE · PREVIEW-ONLY' : 'КАРТОЧКА КЛИЕНТА · CRM';
  if (kind === 'campaign') {renderCampaignDetail(item);return;}
  const grid=node('div','detail-grid'),main=node('div'),side=node('aside','detail-side');
  if (kind === 'work') {
    main.append(detailSection('Текущий контекст',item.currentContext),detailSection('Последний результат',item.lastResult),detailSection('Следующий шаг',item.requiredNextAction));
    if (item.blockers?.length) {
      const section=node('section','detail-section');section.append(node('h3','','Что блокирует работу'));
      for (const blocker of item.blockers) section.append(node('p','blocker',blocker.requestedAction || 'Ожидание внешнего действия'));main.append(section);
    }
    main.append(nativeObservationPanel(item));
    side.append(metadata([['Этап',columnLabels[item.column] || 'Неизвестно'],['Ответственные',item.owners?.map(ownerLabel).join(', ') || 'Пока не назначены'],['Источник','Нативная работа OpenRig']]));
    side.append(node('div','detail-note','Ответы, уточнения и диалог с оператором пока недоступны. Эта карточка открыта только для просмотра.'));
    const source=node('details','detail-provenance');source.append(node('summary','','Связь с источником'),node('p','',item.id));side.append(source);
    state.modal.version=item.version;
  } else {
    main.append(detailSection('Контакты',[item.email ? `Email: ${item.email}` : 'Email не указан',item.phone ? `Телефон: ${item.phone}` : 'Телефон не указан'].join('\n')));
    if (item.surname?.technicalValue) main.append(node('p','technical-note','Фамилия не подтверждена. Техническое значение CRM не является сведением о клиенте.'));
    if (item.attributes?.crmType) main.append(detailSection('Категория CRM',item.attributes.crmType));
    main.append(detailSection('Связанные работы','Связи с работами для этой записи пока не подключены.'));
    side.append(metadata([['Тип',item.kind === 'organization' ? 'Организация' : 'Физическое лицо'],['Источник','CRM'],['Изменено',item.modifiedAt || 'Не указано']]));
    try {
      const url=new URL(item.sourceLink);
      if (url.origin === 'http://127.0.0.1:18082' && /^#(Contact|Account)\/view\/[A-Za-z0-9_-]+$/.test(url.hash)) {
        const link=node('a','source-link','Открыть в CRM ↗');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';side.append(link);
      }
    } catch {}
    if (item.provenance?.import) {
      const source=node('details','detail-provenance');const ref=item.provenance.import;
      source.append(node('summary','','Происхождение записи'),node('p','',`Источник: ${ref.sourceIdentity}\nСтрока: ${ref.logicalRow}\nВерсия сопоставления: ${ref.mappingVersion}`));side.append(source);
    }
    side.append(node('div','detail-note','Изменение записей выполняется в CRM. Эта страница ничего не сохраняет и не дополняет автоматически.'));
  }
  grid.append(main,side);$('detail-body').replaceChildren(grid);$('detail-body').scrollTop=scroll;
  if (kind === 'work' && observationFocus) $('detail-body').querySelector(observationFocus)?.focus({preventScroll:true});
}
function renderCampaignDetail(item) {
  if (item.mode !== 'FIXTURE') {renderDetailError('Режим материала не подтверждён.');return;}
  const root=node('div','campaign-detail');root.append(fixtureLabels(item.labels));
  const facts=node('div','campaign-facts');facts.append(metadata([['Канал','Email · предпросмотр'],['Аудитория','Не выбрана · число получателей недоступно'],['Отправитель','Не настроен'],['Сервис рассылок','Не подключён · provider ID отсутствует']]));root.append(facts);
  const tabs=node('div','preview-switch');tabs.setAttribute('role','group');tabs.setAttribute('aria-label','Формат материала');
  const preview=node('div','email-preview-panel');
  const frame=node('iframe','email-preview-frame');frame.title='Предпросмотр письма — FIXTURE, не утверждено и не отправлено';frame.setAttribute('sandbox','');frame.setAttribute('referrerpolicy','no-referrer');frame.srcdoc=item.previewDocument;preview.append(frame);
  const text=node('pre','campaign-source',item.plainText);text.hidden=true;
  const manifest=node('div','campaign-manifest');manifest.hidden=true;
  manifest.append(node('p','detail-note','Исходный манифест r01 сохранён без изменений. Описания прежнего состояния приложения — исторические, а не текущий статус интеграции.'),node('pre','campaign-source',item.manifest));
  const views=[['HTML-предпросмотр',preview],['Текст письма',text],['Исходный манифест',manifest]];
  for (const [label,panel] of views) {
    const tab=button(label,() => {for(const [_,other] of views) other.hidden=other !== panel;for(const sibling of tabs.children) sibling.setAttribute('aria-pressed',String(sibling === tab));},'secondary-button');
    tab.setAttribute('aria-pressed',String(panel === preview));tabs.append(tab);
  }
  root.append(tabs,preview,text,manifest);
  const caveats=node('section','detail-section');caveats.append(node('h3','','Ограничения и источники'));
  for (const caveat of item.caveats) caveats.append(node('p','',caveat));
  for (const source of item.sourceLinks) {
    if (!['https://www.delfin-tour.ru/promo/5443.html','https://www.delfin-tour.ru/tours/24676.html'].includes(source.url)) continue;
    const link=node('a','source-link',source.title+' ↗');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';caveats.append(link);
  }
  const materials=node('details','detail-provenance');materials.append(node('summary','','Исходные материалы r01 (только чтение)'));
  for (const material of item.materials) {
    const show=button(material.name,async () => {
      try {const {data}=await api('/api/campaigns/'+encodeURIComponent(item.id)+'/materials/'+encodeURIComponent(material.name));
        if (state.modal?.id !== item.id) return;
        const raw=node('pre','campaign-source',data.content);materials.append(raw);show.disabled=true;
      } catch {if(state.modal?.id===item.id) materials.append(node('p','','Материал недоступен.'));}
    },'text-button');materials.append(show);
  }
  caveats.append(materials);root.append(caveats);$('detail-body').replaceChildren(root);
}
function openDetails(kind,id,trigger) {
  state.modal={kind,id,version:null};state.trigger=trigger;
  $('detail-mode').textContent='Режим просмотра';
  $('detail-title').textContent='Подробности';$('detail-body').replaceChildren(node('div','skeleton'),node('p','loading-label','Загружаем подробности…'));
  $('detail-dialog').showModal();$('close-detail').focus();loadDetail();
}
async function loadDetail() {
  if (!state.modal) return;
  const request=++state.modalRequest,session=state.session,{kind,id}=state.modal;
  try {
    const {data}=await api((kind === 'app' ? '/api/board-tasks/' : kind === 'work' ? '/api/board/' : kind === 'campaign' ? '/api/campaigns/' : '/api/clients/')+encodeURIComponent(id));
    if (request !== state.modalRequest || session !== state.session || state.modal?.id !== id) return;
    renderDetail(kind,data);
  } catch(error) {
    if (request !== state.modalRequest || session !== state.session || state.modal?.id !== id) return;
    if (error.status === 401 || error.status === 403) {resetSession(errorText(error));return;}
    renderDetailError(errorText(error));
  }
}
for (const id of ['close-detail','done-detail']) $(id).addEventListener('click',() => $('detail-dialog').close());
$('detail-dialog').addEventListener('click',event => {if(event.target === $('detail-dialog')) {const rect=event.target.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom) event.target.close();}});
$('detail-dialog').addEventListener('close',() => {
  const selected=state.modal?.id;state.modal=null;state.modalRequest++;
  if (state.trigger?.isConnected) state.trigger.focus({preventScroll:true});else if(selected) restoreCardFocus(selected);
  state.trigger=null;
});


// Application conversations are independent from the native execution projection.
async function loadAppTasks() {
  if (!state.token || !state.boardAccess?.read || state.appBusy) return;
  const session=state.session;state.appBusy=true;$('app-tasks').hidden=false;
  try {
    const {data}=await api('/api/board-tasks');
    if (session !== state.session) return;
    state.appTasks=data.items;
    const items=document.createDocumentFragment();
    for (const item of data.items) {
      const card=button('',() => openDetails('app',item.id,card),'task-card');card.dataset.objectId=item.id;
      card.append(node('span','task-kind','Обсуждение · OpenTour'),node('h3','',item.title),node('p','',item.description));items.append(card);
    }
    if (!data.items.length) items.append(node('p','','Доступных обсуждений пока нет.'));
    if (!data.complete) items.append(node('p','','Показана часть доступных задач.'));
    $('app-task-list').replaceChildren(items);$('app-task-status').textContent='Обновлено в '+timeLabel();
  } catch(error) {
    if (session !== state.session) return;
    if (error.status === 401 || error.status === 403) {resetSession(errorText(error));return;}
    $('app-task-list').replaceChildren();$('app-task-status').textContent='Обсуждения недоступны. Обновите данные, чтобы повторить чтение.';
  } finally {if (session === state.session) state.appBusy=false;}
}
const deliveryLabels={pending:'Ожидает доставки агенту',delivered:'Контекст доставлен в очередь агента',failed:'Доставка отклонена до отправки',unknown:'Результат доставки неизвестен — требуется сверка'};
function renderAppTask(item) {
  const scroll=$('detail-body').scrollTop;
  $('detail-mode').textContent=state.boardAccess?.respond ? 'Ответ сохраняется в OpenTour' : 'Режим просмотра';
  $('detail-title').textContent=item.title;$('detail-eyebrow').textContent='ОБСУЖДЕНИЕ ЗАДАЧИ · OPENTOUR';
  const root=node('div','app-task-detail');
  root.append(detailSection('Задача',item.description),node('p','detail-note','Ответ сохраняется в OpenTour. Доставка контекста не подтверждает работу агента и не разрешает бизнес-действие.'));
  const history=node('section','app-history');history.setAttribute('aria-label','Обсуждение задачи');
  for (const message of item.messages) {
    const entry=node('article','app-message');entry.dataset.messageId=message.id;
    entry.append(node('h3','',({request:'Запрос',answer:'Ответ',comment:'Комментарий'})[message.kind]),node('p','message-body',message.body));
    if (message.reply_to) {const request=item.messages.find(m => m.id === message.reply_to);entry.append(node('p','detail-note','Ответ на запрос: '+(request ? request.body : 'Предыдущий запрос этой задачи')));}
    entry.append(node('p','detail-note','Сохранено · '+(deliveryLabels[message.delivery.state] || 'Доставка не подтверждена')),
      node('p','detail-note','Обработка агентом: '+(message.delivery.processing === 'received' ? 'получение контекста подтверждено' : 'не подтверждена')));
    history.append(entry);
  }
  if (!item.historyComplete) history.append(node('p','','Показаны последние 100 сообщений; история неполная.'));
  root.append(history,button('Обновить обсуждение',() => loadDetail()));
  if (state.boardAccess?.respond) {
    let draft=state.drafts.get(item.id);
    if (!draft) {draft={text:'',replyTo:[...item.messages].reverse().find(m => m.kind === 'request')?.id || '',requestId:null,frozen:null};state.drafts.set(item.id,draft);}
    const form=node('form','app-response');
    const label=node('label','','Ответ или комментарий');label.htmlFor='app-response-text';
    const target=node('select','observation-select');target.id='app-response-target';target.setAttribute('aria-label','Связь ответа с запросом');
    const generic=node('option','','Комментарий к работе');generic.value='';target.append(generic);
    for (const message of item.messages.filter(m => m.kind === 'request')) {const option=node('option','','Ответить: '+message.body.slice(0,100));option.value=message.id;target.append(option);}
    if (draft.replyTo && ![...target.options].some(option => option.value === draft.replyTo)) {const earlier=node('option','','Ответ на предыдущий запрос задачи');earlier.value=draft.replyTo;target.append(earlier);}
    target.value=draft.replyTo;
    const input=node('textarea');input.id='app-response-text';input.maxLength=4000;input.required=true;input.value=draft.text;
    const status=node('p','connection-status');status.setAttribute('role','status');
    const submit=node('button','primary-button',draft.frozen ? 'Повторить сохранение' : 'Сохранить ответ');submit.type='submit';
    if (draft.frozen) {input.readOnly=true;target.disabled=true;status.textContent='Сохранение пока не подтверждено. Повтор использует тот же запрос и не дублирует сообщение.';}
    input.addEventListener('input',() => {draft.text=input.value;});
    target.addEventListener('change',() => {draft.replyTo=target.value;});
    form.addEventListener('submit',async event => {
      event.preventDefault();if(submit.disabled) return;
      const session=state.session;
      if (!draft.frozen) {draft.requestId=crypto.randomUUID();draft.frozen={requestId:draft.requestId,kind:draft.replyTo ? 'answer' : 'comment',text:draft.text,...(draft.replyTo ? {replyTo:draft.replyTo} : {})};}
      submit.disabled=true;input.readOnly=true;target.disabled=true;status.textContent='Сохраняем…';
      try {
        await api('/api/board-tasks/'+encodeURIComponent(item.id)+'/messages',{body:draft.frozen});
        if (session !== state.session) return;
        state.drafts.delete(item.id);announce('Ответ сохранён в OpenTour. Доставка агенту учитывается отдельно.');
        if(state.modal?.kind === 'app' && state.modal.id === item.id) await loadDetail();
      } catch(error) {
        if (session !== state.session) return;
        if (error.status === 401 || error.status === 403) {resetSession(errorText(error));return;}
        if ([400,413,415].includes(error.status)) {
          draft.frozen=null;draft.requestId=null;input.readOnly=false;target.disabled=false;
          status.textContent='Ответ не сохранён. Исправьте текст и попробуйте снова.';submit.textContent='Сохранить ответ';
        } else {status.textContent='Сохранение не подтверждено. Текст сохранён в этой вкладке. Повторите тот же запрос.';submit.textContent='Повторить сохранение';}
      } finally {submit.disabled=false;}
    });
    form.append(label,target,input,node('p','field-hint','Не вводите пароли и ключи доступа. Закрытие окна сохраняет черновик в этой вкладке.'),submit,status);root.append(form);
  }
  $('detail-body').replaceChildren(root);$('detail-body').scrollTop=scroll;
}
