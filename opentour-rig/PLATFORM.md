# Архитектура и процесс OpenTour

## v0.6 — Технический доступ, инструменты и непрерывный путь

### Изолированный read-grant для локальной проверки

DevOps/QA вправе создать task-owned краткоживущий application read-grant для изолированного loopback backend и проверки в пределах проекта opentour. Предпочтительно переиспользовать проверенный process-local способ tools/ui_browser_probe.py; если документированному запуску нужен --auth-file, допустим отдельный временный файл в private каталоге с mode0700, сам файл mode0600, с высокоэнтропийным случайным токеном и только его hash в grant. Scope — роль user, чтение opentour в этой локальной проверке. Жизненный цикл заканчивается завершением проверки/остановкой выделенного сервера и отзывом/удалением только task-owned grant; не выдавать предполагаемую автоматическую TTL за реализованную функцию. Секретные значения не попадают в Git, argv/URLs, общие отчеты, screenshots или чат. Указать только безопасную ссылку/назначение и cleanup.

Такой grant не создает внешний аккаунт, CRM principal, native human identity или полномочия реального менеджера. Он не разрешает CRM writes, native reply/decision, рассылку или deploy. Для live read используется только уже разрешенный private CRM credential reference и существующий GET-only adapter; не создавать новый upstream доступ по этой норме. При отсутствии CRM reference продолжаются синтетические и доступные board проверки с честным scope. Не отключать auth/origin/RBAC проверки глобально. Отсутствие application auth-file само по себе не является human gate и не оправдывает поиск по всем owner credentials.

### Инфраструктура до применения

Переиспользовать существующие backend/probe/launcher и сделать один короткий prepare/run/check/collect/cleanup путь. Инструмент готовит все fixture/config/auth inputs до внутреннего окна выполнения, проверяет readiness, сохраняет безопасный результат/диагностику, убирает только свои ресурсы. Внутренний timeout начинается после готовности; внешние пользовательские сроки сохраняются. Повторяемое затруднение сразу получает инженерного владельца и инфраструктурный приоритет до QA/интеграции/применения. Не строить второй auth service, task tracker, controller или универсальный framework ради локальной проверки.

QA проверяет функциональный результат и затронутый риск. При неизменном принятом пути переиспользуются receipts; ручной повтор полного набора хэшей на каждой передаче не является отдельным gate. Существенная identity/integrity ошибка исправляется, а не игнорируется. Обычная синтетическая отладка не имеет агентских квот числа тестов/вызовов или авторских/QA CPU pools. Реальные provider/host/user ограничения, input-size и timeout зависания остаются по назначению.

### План, передачи и merge

Локальный blocker привязывается к конкретной операции/результату. Lead поддерживает следующий полезный backend/native/import/campaign шаг по SPEC/UI_FLOW без фиксированного общего PR budget. Ожидание live UI не останавливает проектирование и реализацию разрешенных read/refresh путей, контрактов native actions, синтетических authorization/idempotency сценариев или masked read-only диагностику409. Не выполнять реальные native writes без действительной human/object authorization и не повторять импорт с неизвестным эффектом.

DEVELOPMENT.md и актуальные TEAM/guidance определяют разрешенный commit/push/PR/QA-led merge. Старое агентское no-merge заменяется на текущем задании со ссылкой на новое основание; оно не создает повторный human gate. Явный более поздний пользовательский запрет сохраняется. Технический PASS достаточного scope ведет к интеграции после применимой проверки совместимости, не к новой общей волне QA. Автор не принимает собственную реализацию.

### Часовая диагностика полезного выхода

Существующий hourly Lead watchdog проверяет полезный результат, пустой actionable frontier при незавершенной миссии, idle с исполнимой задачей, слишком широкие/устаревшие блокеры, конфликтующие старые поручения, инфраструктурный PR без применения и повторные отказы до начала сценария. Один запущенный сервис или одна корректно припаркованная задача не доказывают движение остальных потоков. В текущей проверке Lead снимает ложную зависимость, обновляет агентское ограничение, назначает подготовленный независимый scope, приоритетно исправляет инструмент или будит действующего владельца. Роль Lead не становится каждым-run/merge approval.

При реальном вопросе полномочий — один конкретный human ask и продолжение независимых шагов. Очередь/PR/run receipts дают время ожидания/исправлений, отказы до сценария и завершенные пользовательские этапы, без нового tracker и без записи здоровых проверок. Recovery подтверждается listening/readiness плюс реальным потребительским действием и согласованной queue custody; изменение карточки/доставка контекста сами по себе не являются восстановлением. Watchdog-сообщение обновляется in place без второго scheduler.

### Окна Codex — актуальное решение пользователя

Автоматизация закрытия предложений сменить модель пользователем отложена как нецелесообразная. Не начинать maintainer/tooling проект для нее повторно. При появлении окна отличать его от свежего quota отказа, сохранить модель/сессию/задачу, кратко подсветить конкретное окно пользователю и продолжать независимую работу. Закрытие окна пользователем требует сверки фактического resume и старого blocker, не произвольного пятичасового ожидания. Реально подтвержденный quota reset и failed wake обрабатываются существующим v0.5 восстановлением; старый banner не является свежей проверкой.

## Продолжение работы и обращение к человеку — 2026-11-09

Завершение PR, slice, миссии или отдельного поручения не означает остановку проекта. Пока согласованный пользовательский результат не достигнут и пользователь не остановил работу, Lead поддерживает ближайшую исполнимую работу, а профильные исполнители продолжают свой мандат конечными native qitems. Не начинать новые продуктовые направления ради занятости; интеграция внешнего UI-прототипа ждёт отдельного сообщения пользователя, но независимая backend/data работа продолжается.

Перед постановкой external blocker или вопросом пользователю владелец сам исследует доступные источники, инструменты, предыдущий опыт и разумные обратимые варианты в пределах полномочий. В передаче кратко указывает, что проверено/попробовано, что выяснено, какое точное решение осталось недоступно и какую операцию оно блокирует. Нет обязательного числа попыток; не повторять бессмысленно одно и то же. Реально запрещённое действие не выполняется ради попытки: проверяются допустимые альтернативы, а точная граница полномочий объясняется. Неизвестность и отсутствие идеального подтверждения сами по себе не являются human gate.

Техническое решение внутри мандата принимает исполнитель, проверяет его эффект, сохраняет основания/неопределённость и продолжает работу. Через оператора пользователю передаётся информационное уведомление о существенном выборе и последствиях, а не запрос повторного согласования. Отсутствие зарегистрированного human channel не останавливает техническую работу: оператор сохраняет update и использует действующий разговор/доступный маршрут. Ожидание человека допустимо лишь для реально необходимого решения вне полномочий после предпринятого исследования; оно блокирует только зависимую операцию.

Факты об исходных данных можно самостоятельно проверять в разрешённых локальных оригиналах, заголовках, структуре, содержимом ячеек и сохранённых mapping/lineage, не раскрывая персональные данные в общих материалах. Правдоподобное отображение полей оформляется как выведенное правило с проверкой и неопределённостью; неизвестную историческую provenance не выдумывать и не делать условием всей дальнейшей поставки. Текущий вопрос source-owner-lineage-column-roles больше не требует ответа пользователя: Data Engineer исследует его самостоятельно, сообщает через оператора выбранное правило/остаточные ограничения и продолжает пригодную часть работы. Это не разрешает слепой повтор неизвестно завершившихся CRM-мутаций.

При завершении или блокировке шага владелец выбирает следующий подготовленный шаг своей ответственности либо передаёт Lead точный следующий результат. Lead не закрывает координацию как no-follow-on, оставив незавершённый результат без продолжения. Если допустимой работы действительно нет, фиксируются конкретные исчерпанные альтернативы и условие возобновления. Пустая очередь не доказывает завершение продукта; очередная запись о blocker не заменяет поиск следующего шага. Обязательство реализуется конечными заданиями, без фиктивной занятости и бесконечного исследования.

## Продуктовые контракты

[ARCHITECTURE.md](../docs/ARCHITECTURE.md) описывает компоненты, границы, пользовательские права, отображение работы и зависимости. [UI_FLOW.md](../docs/UI_FLOW.md) задаёт экраны и состояния прототипа. Ниже сохраняются технические процедуры реализации и эксплуатации; при расхождении старых формулировок о user применяются согласованные UI-права от 2026-11-09.

## Границы компонентов

Готовая CRM -> CRM adapter -> локальный integration backend -> рабочий UI. Существующий mailer -> campaign adapter -> драфты/status/links. OpenTour DB владеет app-facing board tasks, requests, answers/comments и явными links; для релевантного контекста назначенному агенту она хранит только lifecycle outbox-сообщения: enqueue, delivery attempt и terminal delivery receipt. Receipt terminal только после подтверждения фиксированной native очередью принятия scoped context message и durable записи возвращённого qitem ID как execution reference. Receipt не доказывает прочтение, выполнение работы, завершение board task или полномочие на бизнес-действие. Неизвестный результат доставки сверяется по стабильному ключу до повтора. OpenRig queue владеет execution custody, ownership/progress/result выполнения и native action evidence; UI может показывать их только как read-only projection. Native qitem IDs не являются источником для восстановления board-разговора. Телефония подключается позднее отдельным adapter. Связи хранят source system/external ID/revision, correlation/request ID, observed time и качество; бизнес-факты не пересоздаются в конкурирующих системах.

Backend выполняет auth/RBAC, нормализацию/сопоставление, идемпотентные операции, retry/readiness, приватное чтение и bounded projections. Агенту не нужно разбирать Excel или опрашивать провайдера вручную на каждом шаге. Пример минимального интерфейса: список/краткая карточка клиента; work item/detail; operator conversation; pending decision/reply; campaign draft/revision/preview. Это требования, не утверждение существующих routes/API.

## Передача результата и ответственность Lead после завершения шага

Lead сохраняет отдельный активный native qitem на согласованный результат текущего этапа. Передача конечного задания исполнителю не закрывает это обязательство. В qitem указаны результат, текущий план/доказательства и ближайшее действие. Пока результат не достигнут, Lead выполняет полезную работу либо удерживает обязательство на конкретной живой зависимости через native queue block. Не оставлять формальный in-progress без работы. Завершение или передача дочернего qitem пробуждает Lead; он сверяет цепочку и привязывает ожидание к фактическому продолжению без дублирования исполнителя.

Каждое конечное назначение содержит адрес возврата и ID обязательства Lead. Контекст сохраняется при передачах Developer → QA Code → System QA → QA Code. После merge QA Code возвращает Lead commit/PR, проверенный результат, ограничения и evidence через native handoff-and-complete с обычным пробуждением. Lead не становится дополнительным согласующим merge. Возврат исследования или другой последней операции подчиняется тому же правилу. Использовать поддерживаемые native команды и их текущую справку.

Получив итог, Lead до завершения своего хода сопоставляет его с продуктовой целью и назначает следующий полезный шаг либо продолжает уже существующий. Обязательство этапа остаётся на фактической зависимости. no-follow-on допустим для законченного отдельного результата, когда продолжение уже имеет активного владельца; он не закрывает незавершённое обязательство Lead. Узкий scope законченной задачи не отменяет постоянный мандат выбирать следующую работу. Если разрешённого продолжения действительно нет, фиксируются исчерпанные альтернативы, условие возобновления и supported wake для удерживаемого обязательства. Явная остановка пользователя сохраняет приоритет. Не нужны задачи ради занятости, повторные QA или новый tracker/controller.

Почасовой watchdog — страховка, не штатный запуск следующего шага. Исправление проверяется на реальном результате: итог доставлен и принят Lead, обязательство этапа сохранено, следующий полезный шаг имеет владельца и фактически начат без нового запроса пользователя и ожидания часового тика. Установка инструкций или отправленный reminder сами по себе не доказывают исправление.

## Выбор CRM и стека

Локальный кандидат выбран по bounded synthetic run: EspoCRM `10.0.11` + MariaDB `11.4.13`, Compose definition in `local/crm/compose.yaml`, evidence and operation boundary in `local/crm/README.md`. It ran on the ARM64 host from the official multi-platform image; manager API role read/created email-only and phone-only Contacts, while native CSV import was admin-only (manager upload returned 403). Admin import completed synthetic rows and records survived restart and database-plus-files restore. Import “Create Only” replay duplicated a record, so import resume must reconcile against CRM state before retry. SuiteCRM `8.10.2` API create/read worked with synthetic data after OAuth keypair setup, but its tested community Docker image was AMD64-only; non-admin/UI import paths were not exercised. EspoCRM core is AGPLv3; the Advanced Pack is separate and not required for this contact/API/import path. Do not treat either candidate run as owner-data import or production acceptance. Source and license references: [EspoCRM Docker](https://docs.espocrm.com/administration/docker/installation/), [EspoCRM import](https://docs.espocrm.com/administration/import/), [EspoCRM license](https://github.com/espocrm/espocrm), [Advanced Pack](https://www.espocrm.com/extensions/advanced-pack/), [SuiteCRM releases](https://docs.suitecrm.com/8.x/admin/releases/8.10/), [SuiteCRM API auth](https://docs.suitecrm.com/developer/integration-api/v8/authentication/). No Frappe comparison was needed to resolve the observed selection.

Существующий open-source mailer, домен и VPS есть по словам пользователя; имя/API/credentials неизвестны. Selectel — арендованный почтовый шлюз, не доказательство названия mailer. Campaign Operator исследует именно имеющийся сервис после идентификации. Пока permitted fixture-adapter явно возвращает FIXTURE и локальный draft ID; реальные provider IDs/status не выдумываются. Название туроператора «Олян» — UNRESOLVED, самостоятельное исправление запрещено.

## Мост к ядру OpenRig — ранняя техническая проверка

Developer/DevOps в третьем slice исследуют текущие поддерживаемые CLI/API/gateway и модель доступа. Проверить live identity kernel, различие operator.agent/operator.human и допустимый маршрут именно пользователя. Не выбрать agent terminal только по имени. Новый manager UI не получает произвольный shell/daemon token или права всех kernel seats. Сессия пользователя связывается с проверенным human identity и project scope; запросы адресуются существующему kernel Operator и далее OpenTour native work.

В одном реальном тесте диалог доставляет поручение в ядро, реальный ответ виден менеджеру, human decision записывается и продолжает исходную задачу после refresh/restart без дублирования. Если установленная версия не дает безопасного поддерживаемого маршрута, зафиксировать конкретный capability gap/engineering task. Fixture chat не засчитывать. Старый unmaintained web UI не является принятым transport contract.

Доска агрегирует native custody/status в понятные человеку работы: инженерные mission/slice либо кампании со связанными поручениями, без автоматического вывода каждого qitem. Точное соответствие фактической модели планирования проверяется перед реализацией. Видны роли, awaiting-human, блокировки и материалы; нет drag-and-drop, анимация отображает подтверждённые изменения. Administrator пишет в контекстные диалоги, user читает их; оба отвечают и уточняют доступные карточки, с отдельной проверкой backend permissions. Восстанавливаемый cache допускается; второй writable task/approval tracker — нет. Действия UI используют штатные команды/доступный supported API с проверкой scope, idempotency и текущего состояния. Ответ на карточке не считается решением, пока native receipt не подтвержден.

## Данные и импорт

`.artifacts/` — уже существующие пользовательские источники. Только чтение оригиналов; import пишет отдельные private outputs, происхождение file/content ID + sheet/row + mapping version сохраняется. Сначала безопасная структурная инвентаризация; не печатать содержимое, пароли, email/телефоны/имена или имена чувствительных файлов в общие evidence. Не публиковать полный file inventory. Реальные файлы разрешены для разработки/тестов; synthetic fixtures для Git/общей приемки.

Минимум пригодной записи — email или phone. Нормализовать явный формат без предположений о неизвестной стране/владельце; invalid/unknown не превращать в valid. Дедупликация сохраняет source lineage, конфликты и неопределенные совпадения; ambiguous matches не сливать молча. Пропуски не обогащать. Import dry-run/quality summary -> reversible import в выбранную CRM -> повторный запуск без дублей. Источники не изменять, существующие контакты не перезаписывать без явной политики.

Текущие входы — три CSV UTF-8 с BOM из двух уже преобразованных пользователем Excel; значения ячеек, не формулы. Использовать CSV напрямую, оригиналы сохранять; ожидание пароля для этого пути больше не действует. Пользовательские counts в SPEC.md — исходные ориентиры, не measured quality. Проверить dialect/header/quoted multiline cells и logical record count; BOM не входит в имя первого поля. Телефоны читать как текст, не терять ведущие нули/+ и не применять numeric coercion. Не пересчитывать формулы и не заявлять эквивалентность Excel без отдельной проверки. Источник преобразования — workbook/sheet/CSV revision; имя файла не заменяет lineage.

Для будущего зашифрованного входа без доступного преобразования остается локальный ENCRYPTED_PENDING_INPUT, не общий стоп. Неизвестное согласие на канал не равно разрешению отправки; unsubscribe/suppression принадлежит mailer и учитывается при будущей отправке, не обходится очисткой контакта в CRM.

## Campaign draft и материалы

Creative формирует первый оффер как часть сценария: нет готового предложения, которое можно считать утвержденным. Записывать источник/время/валюту/цену/условия/изображения/права/проверенность. Неподтвержденное помечать preview-only и не выдавать за продаваемое наличие. Designer создает HTML-email с текстовой альтернативой/asset refs по реальной потребности. Preview не делает запросы к tracking URLs/реальным клиентам; небезопасный HTML не исполняется в рабочем приложении. Manager запрашивает правки либо принимает конкретную revision. Acceptance контента не вызывает send; send должен быть отдельным явно авторизованным этапом с финальной проверкой аудитории/отписок/оффера.

## Локальные среды и права

Local CRM Compose is now specified in `local/crm/compose.yaml`: app binds only to `127.0.0.1:18082`, DB has no published port, app waits for DB health, and app health uses EspoCRM `app-check`. Both image references are versioned and digest-pinned; Compose owns four named volumes and a project network. Passwords are local Compose secret files under ignored `local/crm/secrets/`; source CSVs are not mounted, and imported records/backups are private customer data. `local/crm/README.md` documents setup, readiness, stop semantics and separate-project restore. This is an owned local candidate environment, not a production deployment or an authorization to import owner files. Never clean user sources or unrelated services.

administrator управляет подключениями/локальными аккаунтами, user видит только положенный scope и не вызывает admin APIs напрямую. Секреты не оказываются в браузере/argv/logs/Git. Оба могут быть одним физическим владельцем, но роли и проверки различаются. Нет утверждения production security. Сейчас локально; VPS, credentials сервисов, mass send, SMS/мессенджеры/телефония не активируются этой спецификацией.

## SDLC и накопление опыта

Одна mission с пятью результатными slices. Queue владеет работой/передачами, native proof — attributed judgments, SPEC — intent/contracts, PROGRESS — краткая история, NOTES — только реально полученные знания. Отдельный slice на сообщение/hash/handoff не нужен. Автор не принимает свою часть. QA Code ведет независимое review/repair и выполняет merge после успешных необходимых проверок. С 2026-11-09 push рабочих веток в существующий remote разрешён; изменения интеграционной ветки проходят PR. QA Code выполняет merge после успешного необходимого независимого QA без отдельного подтверждения пользователя. Deploy отложен. Правила — [DEVELOPMENT.md](../docs/DEVELOPMENT.md).

Перед расширением компонента проверить существующий путь и переиспользование; не копировать новый integration stack на каждый канал. Небольшой локальный refactor делать с сохранением поведения/контрактов; широкий — отдельная задача по конкретной причине. Независимые проверки по измененному поведению, не полный повтор всего на каждую правку. Образ/receipt определяются фактическим launcher, без многократного ручного переписывания хэшей. Возврат дефекта оставляет автору исполнимый следующий шаг; preparation и execution не ждут друг друга циклически. Priority не кодируется фиктивной hard dependency.

Текущая работа — только спецификация. Нативное scaffold/validation не является запуском, коммерческим результатом, готовностью bridge или одобрением моделей/permission policy.

## v0.2 — Практики исполнения и предотвращения остановок

### План, роли и зависимости

Lead ведет пополняемый ближайший план от результата менеджера; готовит следующий независимый scope, пока текущий проходит QA. Число slices/PR первой миссии не является общим stop condition. Creative/Designer/DE/Developer/Campaign Operator напрямую передают профильную работу. Стоимость, новые доступы, send и deploy остаются отдельными решениями; обычные действия внутри фактически назначенного scope не требуют повторного допуска Lead. До выбора моделей/effort и явного запуска никакой standing execution не активируется.

У hard dependency указывается конкретный необходимый output; priority/занятость общего checkout не превращаются в фиктивную функциональную связь. Локальный gap блокирует только зависимое применение. У исправления всегда есть исполнимый owner/next action. Queue передает custody, сообщение только информирует; для передачи использовать поддерживаемый native handoff. Реальное human решение отдельно от доставки сообщения и обновления карточки.

### Фоновые операции и данные

Импорт/пакетная интеграция сохраняет checkpoint и принятые результаты до продвижения прогресса; restart не повторяет успешные записи. Stable request/job identity и versioned mapping/cache позволяют idempotent resume. Ошибочные строки/batches изолируются, частичное покрытие явно; no-match/unknown не становятся успешным контактом. Повторы read-only/идемпотентных операций ограничены числом попыток/deadline с backoff/jitter и Retry-After; auth/rights ошибки имеют отдельный scope. Мутацию с неизвестным эффектом сначала сверяют с системой назначения, не повторяют вслепую. Текущему малому CSV-импорту не нужен отдельный universal bulk framework; функции добавляются под реальные ошибки/масштаб.

Перед массовой операцией проверить существующие import/export/bulk/API capabilities вместо ручных запросов на каждую запись. У terminal result есть manifest/receipt и доставка владельцу; пропущенный wake восстанавливается штатными средствами OpenRig, повторное потребление идемпотентно. Завершение подтверждается фактической обработкой владельцем, не только сообщением. Не создавать второй controller/scheduler.

### QA, среда и сопровождаемость

QA Code ведет независимый review и применимое System QA, без обязательного двойного полного покрытия. Author/substantial harness repairer не принимает свою часть. Изменение версии инвалидирует затронутые результаты; необходимость полного rerun объясняется impact. Одна проверенная идентичность кандидата/фактического запуска переиспользуется проверяющими; новый запуск проверяет среду автоматически. Циклические freeze/preparation waits запрещены. Локальный refactor сохраняет форматы/ошибки/behavior; широкая консолидация имеет конкретную задачу. Reviewer проверяет дублирование, замененный неиспользуемый код и второй источник истины.

Повторяющиеся команды превращаются в минимальные локальные инструменты с bounded outputs и понятной диагностикой. Реальную нагрузку измеряет DevOps, произвольные численные CPU/RAM quotas Polar не наследуются. Deadline/retry budget определяется операцией, секреты и owner data защищены. Только task-owned cleanup, QA scratch вне repo и `.artifacts/`. Измерять пользу автоматизации по сокращению ручных шагов, межпередачных ожиданий и повторных ошибок; календарное время не называть активными трудозатратами/токенами без измерения.

### Диагностика и опыт доступа

Lead выполняет уже разрешенную ежечасную mission-flow диагностику; DevOps обновляет существующий native watchdog in place без нового согласования cadence или дублирующего job. Дополнительные проверки эффективности определены в v0.6. Проверять реальный прогресс/потерянные передачи/ложные блокеры, не требовать занятости всех seats. Различать symptom, подтвержденный work incident и отдельно доказанную cause. Закрывать по фактическому продолжению работы; recovery не доказывает постоянного устранения причины. Фиксировать только существенные отклонения/меры/проверенный эффект в native mission NOTES, не здоровую проверку или каждый transient. Запрос только статуса не является поручением на вмешательство.

Для доступа переиспользовать разрешенные accounts/sessions, подтвержденные маршруты и ранее данные ответы пользователя. Каждый завершенный login/registration/reauth/session recovery/new-right/access-problem episode кратко фиксировать: результат/что новое или необычное/что блокировало/missing tools/участие человека. Обычный API вызов работающим ключом не новый эпизод. Сначала использовать существующий общий OpenRig access journal, если он доступен и разрешен; иначе безопасные mission NOTES, без еще одного credential store. Никаких паролей, PII, cookies, verification URLs. Timeout/невидимый элемент не равен human gate: проверить form/locale/session/tool compatibility в пределах разрешения. Пользователю — только необходимый точный ввод/действие с сохраненной точкой продолжения.

### Контекст и обновление инструкций

Common + роль + актуальный scope, остальное по адресам и необходимости; не загружать всем всю историю. Queue владеет заданиями, CRM/mailer — фактами, native proof — judgments, NOTES — прожитым опытом. Compact navigation не конкурирует с этими источниками; большие журналы читаются выборочно. После изменения спецификации проверить установленную версию, доставку нужным ролям и фактический эффект отдельно. Эта локальная правка не разрешает установку/регистрацию/запуск. v0.3 model/effort selections and local launch authority below supersede earlier pending-setup statements.

## v0.3 — Isolated account and quota-aware native wake

rig.yaml pins all nine Codex seats to env.CODEX_HOME=/Users/garry/.codex-opentour. This is a directory, not config.toml itself. Its read-only auth status was logged_in; no credentials copied/read/printed. Use the explicitly selected builtin:yolo permissions from v0.4 without changing account/business authority. Do not modify daemon CODEX_HOME, kernel/Polar homes/logins or unrelated jobs. Native startup may write managed project instructions and config/hooks inside the selected home; preserve existing unrelated settings. Builtin role refs resolve locally and must be re-resolved on another installation.

One existing native periodic-reminder targets the actual canonical Lead session every3600seconds for hourly mission-flow diagnosis, including unjustified quota blockers and failed wakes. DevOps maintains/reconciles the job and verifies delivery; Operator bootstraps recovery if needed. A real known future reset may have one attached native continuation wake. No duplicate scheduler, catch-up scans, healthy-check logs or restart against an explicit user stop.

When actual quota exhaustion or imminent exhaustion is known, save current qitems/checkpoint/artifact references and exact next action before waiting. Use the existing native queue block --wake-after at observed reset_at plus a small margin, or the same supported watchdog with a verified next evaluation; do not leave an untimed external:quota blocker. A timed park attaches to the actual continuation, not a second assignment. Account-wide limit should coalesce worker waits at Lead; a successful resume releases eligible current owners via native handoff/resolve with no duplicate invocation. Distinguish account limit, model limit, transient 429, stopped harness and real external/business decision. No blind retry of an email/import mutation with unknown effect.

If reset timing is genuinely unknown, record the missing evidence and perform a bounded diagnostic re-evaluation within one hour using existing scheduling. Do not infer another account's quota from daemon usage. A five-hour token window is not a five-hour mandatory recheck interval. Apply v0.5 below; repeated five-hour parks without fresh evidence are prohibited.

A daemon timer can fire while the model has no quota, but it cannot supply tokens or prove the prompt is accepted. DevOps/Operator must verify supported wake delivery for the actual stopped/limited harness and preserve original session/custody. Do not call a delivered message resumed work: verify a new owner action/result. If automatic post-reset continuation is unsupported, report the exact capability gap/owner instead of claiming continuity works; no undocumented Enter/menu/restart workaround without scope verification. Record actual quota interruption/resume failures and fixes in existing mission NOTES, no per-hour healthy log. Save wake ID/next due in existing continuation/receipt, not a new state service.

Deployment acceptance: correct account home on every seat, exact 2 Sol medium +7 Luna mapping, ready versus startup proof, native backstop ID/target/interval/next fire and a safe test of ordinary reminder delivery without exhausting real quota. Actual five-hour quota exhaustion/reset/resume stays NOT RUN until observed; no manufactured consumption to test it. Operator must report any unresolved native capability, not leave a silent blocked rig.

## v0.4 - Explicit OpenTour permission selection

User explicitly selected builtin:yolo for ALL nine OpenTour seats (Codex danger-full-access, approval_policy=never). This supersedes earlier default-floor/no-YOLO statements. Apply stored effective seat selections and verify actual managed launch flags; rig YAML alone is not proof for existing processes. Preserve work/context at safe boundaries; do not modify kernel/Polar/other homes or account bindings. Native execution capability does not expand business authority: no unapproved campaign send, public/VPS deployment, purchases or disclosure.

## Самостоятельное решение ограничений — 2026-11-09

Принцип — в [CULTURE.md](CULTURE.md). Обнаружив препятствие, агент уточняет, какую именно операцию оно блокирует, исследует доступные возможности и пробует подходящее обратимое решение. Проверяет результат через потребителя. Если решение не сработало, использует полученные сведения для следующей попытки. Независимая работа продолжается. Повторяющееся затруднение становится задачей на улучшение инструмента или процесса.

Исполнитель владеет проблемой до проверенного решения либо содержательной передачи: что установлено, что пробовал, чего конкретно не хватает и кто выполняет следующий шаг. Технические эксперименты не требуют нового согласования каждого варианта внутри уже разрешённого scope. При реальной границе полномочий к человеку передаётся конкретное недостающее решение, а независимая работа продолжается. Исследование не превращается в бесконечные повторы: неработающий подход пересматривается по полученным данным.

### Сохранение опыта

| Где | Что сохранять |
|---|---|
| Mission NOTES.md | Существенная проблема, решение, причина выбора, наблюдаемый результат и оставшиеся ограничения |
| Собственный LEARNED.md | Вывод, который изменит действия агента при следующем похожем случае |
| Код, инструмент или инструкция | Повторяемое решение, которое полезнее автоматизировать или сделать общим |

Отчёт о каждом поиске или неудачной команде не нужен. Сохранять то, что помогает продолжить работу и избежать повторения ошибки; подтверждённый вывод отличать от гипотезы. Изучать относящийся к задаче накопленный опыт перед повторным исследованием. Опыт другого места не записывать за его владельца: передавать вывод, чтобы тот сам осмыслил и сохранил его. Не создавать отдельный approval-процесс или новый tracker ради обучения. Исходные данные и критерии результата сохраняют смысл.

### Пример применения: обязательная фамилия CRM

Прямое решение пользователя: при отсутствии подтверждённой фамилии записывать в обязательное lastName буквальную строку `None` (не null и не выдуманную фамилию). Существующую достоверную фамилию сохранять. Оригиналы не менять; техническую заглушку отличать от факта о клиенте в mapping/quality metadata. Заглушка не участвует как идентификатор в дедупликации и может быть заменена при появлении подтверждённых сведений. Не обращаться повторно за этим уже принятым решением. Проверить приём CRM, отсутствие дублей при повторе и потребление результата; сам mapping policy больше не основание ожидания.

## v0.5 - Model prompts, quota evidence and verified recovery

Automatic handling of Codex model-change suggestions is user-deferred; do not re-create tooling/maintainer work for it. Preserve the approved model, classify the observed dialog, notify the user for manual dismissal and reconcile the same task after recovery. A recommendation is not quota exhaustion; no blind Enter/Escape or five-hour park from that dialog.

Distinguish advisory model prompt, freshly confirmed provider quota exhaustion, failed wake delivery, and an ordinary idle prompt. An old usage banner is historical evidence, not a fresh availability check. Record reset text, observation time, timezone and its basis; use timezone-aware reset_at with date/UTC. A user's confirmed provider-dashboard reset is evidence, not UNKNOWN merely because the terminal omits timezone. For the OpenTour incident, the user confirmed reset at 2026-11-09 04:43 Asia/Bangkok (2026-11-08T21:43Z); preserve this as incident history, never as a recurring schedule.

Hourly Lead diagnosis MUST examine whether a parked quota blocker is still justified, whether reset has passed, and whether a scheduled wake was delivered/consumed. A future timer or blocked queue state does not exempt work from diagnosis. No prohibition on this check may remain in active watchdog text. Use the relevant account/home, not daemon-default usage. Check availability at minimum cost after reset plus a small margin. If reset genuinely remains unknown, one bounded diagnostic re-evaluation is due within at most one hour, using existing scheduling; do not repeatedly park for five hours without new provider evidence. Respect actual Retry-After/future reset and avoid repeated API attempts before it. A diagnostic is not a blind replay of business mutations.

DevOps owns native timer/delivery health, recognized-dialog handling and terminal recovery; Lead owns workflow diagnosis and independent useful continuations. A failed wake routes recovery to DevOps, with existing Operator escalation if DevOps cannot act; the blocked recipient must not be the only recovery target. Coalesce with existing jobs/queue custody, no parallel scheduler or per-seat polling loops. If model quota prevents all in-rig agents from responding, daemon/Operator recovery must remain addressable without relying solely on that exhausted model. Unsupported native recovery becomes a concrete tooling task, not a claim of successful automation.

Recovery requires all three: the harness accepts continuation, the original qitem no longer carries the stale blocker, and the owner actually resumes useful work or hands the prepared result to its consumer. Reconcile obsolete owned wakes so they cannot duplicate work. Resume the same session/task and preserve unknown side effects, candidate artifacts and independent QA. Never mark recovery from a timer fire, cleared window or queue edit alone. Preserve explicit user stop, budgets, credentials, account isolation and business authority. Log only material incidents/actions/results in existing notes; healthy hourly checks remain unlogged.

## Обоснование ограничений и действие после неудачной проверки

В существующем контракте, протоколе или addressed notes, без новой формы согласования, владелец коротко указывает: какое свойство защищает ограничение; определение метрики (включая числитель, знаменатель, применимость и UNKNOWN); откуда взято число и почему оно подходит этому потребителю; это внешняя граница, инвариант или пересматриваемая эвристика; кто и каким следующим действием разрешает отказ/неопределенность. Эвристика не становится внешним запретом из-за возраста записи или слова MUST.

Реальный предел пользователя/провайдера и права доступа сохраняются с первичным основанием. Инвариант корректности проверяется релевантным тестом и не отменяется ради продолжения. Внутреннюю operational настройку пересматривает технический владелец с DevOps по ресурсам; предметную методику — предметный владелец с независимым валидатором/QA по применимости. Не добавлять Lead или человека как нового согласующего обычного технического выбора.

Отказ проверки содержит затронутый путь/claim и конкретное действие: исправить реализацию, доставить данные, выяснить идентичность/применимость, проверить влияние или пересмотреть эвристику с основанием. Недостаток данных адресуется Data Engineer/Data Researcher вместе с исследователем. UNKNOWN не превращать ни в PASS, ни в бессрочное ожидание без исполнимого исследовательского шага. Независимые пути продолжаются. Обход не должен маскировать дефект; предварительная проверка имеет явно ограниченный claim.

Повторяемая ручная операция или созданный, но не используемый инструмент — повод для приоритетного исправления общего механизма и применения через потребителя. Приоритет проходит через разработку, необходимую независимую функциональную QA, интеграцию и использование. Новый tracker, approval gate или таймер для этого не нужен.

## Границы локальной блокировки и выбор следующей работы

Блокировка родительского outcome допустима как описание полной остановки только когда препятствие действительно мешает всем оставшимся разрешенным результатам этого outcome. Иначе паркуется зависимый child/направление; если native родитель уже ожидает child, Lead сохраняет обязанность назначать и потреблять независимую работу. Один dependency park не означает остановку всего плана. Нет требования держать каждого агента занятым или вводить отдельного родителя на каждый шаг.

Завершив или заблокировав направление, Lead в том же ходе сопоставляет состояние с незавершенными требованиями миссии, выбирает следующий полезный результат и назначает либо продолжает существующий конечный шаг. Если реализация пока невозможна, допустимым шагом может быть исследование конкретного недостающего контракта, инструмента или зависимости в пределах полномочий. Не повторять исчерпанную диагностику ради занятости.

external:* обозначает конкретное недоступное внешнее условие. Отсутствие готовой задачи/плана, «ожидание нового actionable outcome» и законченный child не являются внешними зависимостями. Полная остановка требует конкретного объяснения, почему остальные незавершенные результаты миссии также нельзя продвигать, и условия возобновления. Реальные пользовательские ограничения сохраняются.

В существующей ежечасной диагностике проверить: этот blocker мешает всему результату или только последнему выбранному способу/направлению? Исправить слишком широкую зависимость и назначить доступный шаг сейчас, без ожидания следующего тика. Не добавлять отчеты о здоровых проверках.

## Телефонный код по умолчанию и конфликтные записи

Прямая инструкция пользователя от 2026-11-09: при неизвестном телефонном коде использовать +7 по умолчанию. Это согласованная политика преобразования, а не установленная страна/происхождение контакта. Она заменяет прежний запрет на нормализацию только из-за отсутствия explicit country/calling-code metadata; неизвестный код больше не является human gate или общей причиной остановки импорта.

Сохранять оригинальный текст и lineage неизменными; нормализованное значение и признак assumed_calling_code=+7 хранить отдельно в существующем mapping/import evidence. Явно указанный международный код не заменять. Применять проверенный разбор национального/международного формата: не приписывать +7 механически к уже закодированному номеру и не дублировать код/национальный префикс. Неразбираемый или неоднозначный формат явно отмечать на конкретной записи и продолжать остальные.

Data Engineer реализует минимальное версионированное правило в существующем импортере с необходимой независимой QA. После проверки продолжает ранее разрешенный локальный импорт: перед повторной операцией сверяет текущую CRM/checkpoint и использует идемпотентный путь, чтобы не воспроизвести неизвестные эффекты.

Конфликтные записи, включая существующие email/identity/normalization collisions, явно маркировать в действующем quality/disposition механизме с причиной и следующим действием. Не скрывать их и не считать успешно импортированными; не выполнять молчаливое объединение или перезапись существующего контакта. Неразрешенный конфликт удерживает только небезопасную операцию этой записи. Продолжать остальные пригодные записи и независимые backend/data результаты. Уведомление о конфликте не становится запросом пользовательского разрешения на всю работу. Это не разрешает рассылки, звонки, deploy или изменение чужих данных.

## Эволюция процесса, опыт и границы evidence

Источники: действующие правила — каноническая спецификация рига и guidance в репозитории; назначения/владельцы/handoff — native queue; наблюдения и эволюция процесса — docs/operations/process/NOTES.md; применимые краткие выводы — LEARNED.md рига. Git хранит историю правил. Не создавать второй task tracker, process database, approval цепочку или scheduler.

Lead обоих ригов вправе самостоятельно исследовать и исправлять внутренние рабочие процедуры в пределах действующей миссии; исполнители вправе дополнять наблюдения и свои scoped lessons. Lead согласует существенный технический выбор с затронутым владельцем, обновляет каноническое правило и применимые текущие задания, обеспечивает установку через существующие полномочия/оператора и проверяет фактическое действие. Не запрашивать пользователя для обычной процессной коррекции. Нельзя расширять бизнес-полномочия, менять явные пользовательские пределы, научные критерии после исхода или подменять независимую приемку.

На существенное изменение — одна адресуемая запись: проблема и наблюдение; решение/основание; затронутые файлы и commit/версия, когда доступны; фактическое применение/оставшиеся пробелы; ожидаемый эффект; измеренный результат и ограничения сравнения; вывод/следующее действие. Связанные эпизоды дополняют запись, не копируют ее во все журналы. Доставка, применение и полезный эффект — разные утверждения; допустимы «не проверено», «не помогло», «отменено». Восстановление работы не доказывает устранения причины. Коррекции датируются, исходные факты сохраняются.

**Границы evidence.** Собирать только минимальное уже доступное основание конкретного вывода. Обычно достаточно commit/PR/qitem и короткого наблюдения; файл evidence необязателен. Для сравнения сохранить компактные границы окон, определения показателей, существенные counts/IDs и метод вычисления. Запись измерения не требует полного replay, цепочки SHA, manifest на каждый receipt, независимого QA или отдельного PASS. Отсутствие измерений/receipt не блокирует разработку, merge, эксперимент или продолжение миссии: эффект остается непроверенным. Неполная телеметрия не создает отдельный инженерный проект без конкретной повторяемой потери.

Не копировать целые native очереди/транскрипты/скриншоты; не создавать отчет на каждый turn, попытку, здоровую часовую проверку или handoff. Не выполнять сценарий повторно только ради процессного доказательства, если достаточное наблюдение уже есть. Не вводить новые ресурсные/численные квоты на сбор доказательств. Integrity/security/financial проверки продукта сохраняются там, где защищают реальный риск; эти требования не переносятся на приемку журнальной записи.

В Git допускаются только безопасные агрегаты, несекретные ссылки/ID и короткие extracts; credentials, PII, клиентские строки, provider/retained datasets, private oracle и raw traces остаются в разрешенном private storage. Секреты не заменяются хэшами для публикации. Ссылка на private original может дополнять, но не заменяет понятное безопасное основание вывода в репозитории.

Перед похожим изменением прочитать релевантный LEARNED и адресуемый эпизод; применить прежний вывод либо объяснить отличие условий. В LEARNED повышать только условный применимый вывод с основанием; не выдавать непроверенную гипотезу за установленный урок. Использование опыта — изменение действия, не факт чтения файла.

Существующая hourly диагностика рассматривает незавершенные существенные улучшения и полезный выход; новых таймеров/отчетов нет. Не нужно измерять каждую редакторскую правку. Если вмешались другие изменения или scope отличается, не приписывать причинность одному правилу. Queue/PR/receipt timestamps — календарное время, не active compute/tokens. Объем кода и qitems не цель. Затраты на доказательство соразмерны решению; сбор можно остановить с явным ограничением вывода.

Держать рабочий журнал и LEARNED компактными в текущих context budgets, читать по адресам. Законченные старые эпизоды при реальной необходимости переносятся в архив с сохранением IDs/ссылок; не автоматическая ротация по каждой записи. Живые NOTES/LEARNED/evidence не входят в manifest установки и не проецируются как полный обязательный boot context. В загрузку входит краткий LEARNED и адрес раздела политики; детали по запросу.

Действующее правило редактировать на месте, устраняя противоречащую формулировку; Git и запись изменения сохраняют историю. Не наращивать бесконечную последовательность обязательных «amendments» в действующем SOP. Это правило не требует сейчас переписывать всю прежнюю спецификацию. Установка и журнальная работа не останавливают полезное исполнение.
