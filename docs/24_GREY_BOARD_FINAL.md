# Grey Board

Маршрут: `/app/teams/:teamId/board`.

Доступны Agent, Status, People, Risk, Timeline и Source views. Agent View начинается
с pending AI Inbox и объединяет задачи, требующие решения, активные, stale, рисковые
и завершённые.

Карточка показывает исполнителя, дедлайн, статус, источник, confidence, исходное
сообщение, причину identity resolution и YouGile sync status. Из карточки можно
переназначить сотрудника, изменить дедлайн, перевести в работу/blocked/review/done,
запросить статус и открыть внешнюю карточку. Изменения проходят через backend и
BoardMirrorService.
