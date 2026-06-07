# Team Map

Team Map - операционная карта компании, а не HR-оргструктура.

Route: `/app/companies/:companyId/map`.

Backend: `GET /api/companies/{companyId}/map`.

Для каждой команды отображаются:
- open tasks;
- overdue;
- risks;
- YouGile sync health;
- общий цвет состояния.

Цвета:
- green: штатно;
- yellow: есть предупреждения;
- red: есть просрочки или сильный риск.
