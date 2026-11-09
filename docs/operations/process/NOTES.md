# Эволюция процесса OpenTour

Политика: [PLATFORM](../../../opentour-rig/PLATFORM.md#эволюция-процесса-опыт-и-границы-evidence). Рабочие уроки: [LEARNED](../../../opentour-rig/LEARNED.md). Только существенные изменения и наблюдения; native queue сохраняет custody. Ретроспективный синтез внешнего агента с атрибуцией источников, не запись от имени Lead. События ниже UTC; перенос2026-11-10.

## opentour-20261109-outcome-return

**Проблема/решение.** Последний QA/исследовательский child завершался no-follow-on, теряя продолжение. Закреплены normal native return и отдельный outcome qitem-opentour-current-outcome-20261109; исходные наблюдения в mission NOTES, раздел continuity-repair-problem-and-solution-2026-11-09.

**Наблюдение.** DE return11:36:37 и successor qitem-20261109114720-5eb6fecd принят11:47:38.724. Между ними был daemon/tmux recovery; это не uninterrupted post-merge proof. В более позднем историческом snapshot возвраты PR9 и PR10 приняты с задержками26.7 и7.4мин: [данные](evidence/2026-11-09-continuity-observation.json).

**Вывод.** Durable custody и реальный successor подтверждались, но минимальная latency или отсутствие повторного простоя не доказаны. Не путать возврат/установку правила с быстрым полезным продолжением.

## opentour-20261109-phone-independent-work

**Проблема/решение.** Lead припарковал широкий outcome на отсутствии country code. Пользователь разрешил default+7 и явные неблокирующие конфликты; v0.8 ограничила blocker локальным направлением. Поручение qitem-20261109134824-73ed81e3297d53ff.

**Применение.** Независимая Organization ветка стартовала параллельно нормализации. Приняты PR8/9/10; время от открытия до merge соответственно43.2/25.9/7.1мин (не активное время review). QA PR9 вернул два исправленных существенных дефекта. Затем начат реальный migration/import child qitem-20261109162523-93cd197d; его итог при snapshot16:26:12 еще не был установлен.

**Эффект/вывод.** В равных окнах новые queue rows30→15, merges0→3. [Окна/метод](evidence/2026-11-09-continuity-observation.json). Это наблюдаемый полезный выход и параллельность; нельзя приписать весь эффект одному правилу или объявить импорт завершенным. Статус сегодняшнего импорта из этой исторической записи не выводится.

## opentour-20261110-repository-experience

**Решение.** v0.9 закрепляет самостоятельное ведение/использование опыта и минимальный evidence; журнал/LEARNED находятся в этом репозитории. Прежние mission NOTES остаются адресуемым первичным опытом без массового дублирования.

**Применение/эффект.** 2026-11-09T18:54Z оператор обновил installed spec обычным library remove/add: сохранен library id `115895d8be9a6ee3`, rig-package version остается0.2, продуктовая SPEC стала0.9, static manifest32/32 и native spec validation PASS. `rig context work-install --project opentour` возвращает repo `SPEC/CULTURE/LEARNED`; managed root AGENTS обновлен компактными v0.9 common/Lead/culture правилами. Seats не перезапускались; параллельная board/data-ownership работа Lead не затронута. Это подтверждает доставку/доступность, не фактический полезный эффект; он остается UNVERIFIED.

## opentour-20261110-board-conversation-ownership

**Решение.** По пользовательской коррекции OpenTour DB — источник истины для board tasks, requests, answers/comments, явных request↔answer links и durable delivery/processing state. Native queue отвечает за execution custody; qitem IDs могут быть ссылками. История OpenRig не восстанавливает деловой разговор, сохраненный ответ не дает полномочия на действие. Это снимает прежний внешний native-history prerequisite без изменения бизнес-границ.

**Применение.** Lead обновил ARCHITECTURE, UI_FLOW и slice 03 SPEC/PROGRESS. Developer owns implementation child `qitem-20261109190910-488446dc40a06c17`, using private local SQLite as the proportionate starting store; retained outcome `qitem-opentour-current-outcome-20261109` is blocked on that exact child. Operator routed the v0.9 policy-only scoped PR continuation atomically to DevOps as `qitem-20261109191014-71592011` (source `qitem-20261109190846-d470ffea`); QA Code is reserved for independent review.

**Эффект.** Assignment delivery/custody verified; implementation, persistence round-trip, independent QA, merge and user-path effect remain NOT RUN. No DB migration, CRM/native business write, service restart, deploy or campaign send occurred.


## opentour-20261110-board-data-ownership-policy

**Правило.** OpenTour DB owns app-facing board tasks, requests, answers/comments, explicit links, and durable delivery/processing state for relevant agent context. OpenRig queue owns execution custody and native action evidence; qitem IDs may be linked as execution references but do not reconstruct the business conversation. Persisting an answer does not authorize a business action. Source decision: qitem `qitem-20261109190846-d470ffea`; policy implementation: qitem `qitem-20261109191014-71592011`.

**Application status.** The current SPEC and PLATFORM state the boundary. The Lead-owned architecture/UI and slice documents remain outside this change. Delivery of this scoped candidate is recorded; backend persistence, independent review, merge, and consumer effect remain unverified.


## opentour-20261110-context-delivery-boundary-qa-correction

**Finding/correction.** Independent QA of candidate `b58fc205dca6d4bd2f8670c99fd62514dfc62bf3` identified that “delivery/processing state” could be read as a second writable authority for task progress. The v0.9 policy now limits OpenTour DB delivery state to the bounded context-message outbox lifecycle: enqueue, delivery attempt, and terminal receipt. A terminal receipt means the fixed native queue accepted the scoped context message and the returned qitem ID was durably linked as an execution reference. It does not mean read, action, or task completion. Unknown outcomes reconcile by stable delivery identity before retry. OpenRig queue remains authoritative for execution custody, ownership/progress/result, and native action evidence; any app view of execution state is read-only. A receipt does not authorize business action.

**Status.** Policy text is corrected in SPEC and PLATFORM in response to QA qitem `qitem-20261109192014-8a1e119e`; behavior and consumer effect remain unverified pending implementation and independent re-review.
