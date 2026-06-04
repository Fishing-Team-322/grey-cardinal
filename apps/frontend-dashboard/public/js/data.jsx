// Grey Cardinal - mock data (frontend only)

const GC_TRANSCRIPT = [
  { id:'t1', name:'Петя', init:'П', color:'#3b82c4', time:'14:02', text:'Давайте оплату подготовим к четвергу, крайний срок - до конца недели.', status:'final' },
  { id:'t2', name:'Аня', init:'А', color:'#3da37a', time:'14:03', text:'Я проверю интеграцию с YouGile сегодня вечером, примерно к восьми.', status:'final' },
  { id:'t3', name:'Дима', init:'Д', color:'#d68b1c', time:'14:05', text:'Мне нужно до завтра поднять websocket для dashboard.', status:'final' },
  { id:'t4', name:'Петя', init:'П', color:'#3b82c4', time:'14:06', text:'Если оплата зависнет в Todo до среды - это риск для релиза.', status:'proc' },
];

const GC_TRANSCRIPT_EXTRA = [
  { id:'t5', name:'Аня', init:'А', color:'#3da37a', time:'14:08', text:'Тогда вечерний дайджест соберем в пятницу, как обычно.', status:'final' },
  { id:'t6', name:'Дима', init:'Д', color:'#d68b1c', time:'14:09', text:'И еще нужно проверить daemon на Windows перед демо.', status:'final' },
];

const GC_TASKS = [
  { id:'k1', title:'Подготовить оплату', who:'Петя', whoInit:'П', due:'Четверг, 18:00', prio:'High', conf:87, source:'meeting', voice:true },
  { id:'k2', title:'Проверить интеграцию с YouGile', who:'Аня', whoInit:'А', due:'Сегодня, 20:00', prio:'Medium', conf:81, source:'meeting', voice:true },
  { id:'k3', title:'Поднять websocket для dashboard', who:'Дима', whoInit:'Д', due:'Завтра, 12:00', prio:'High', conf:91, source:'meeting', voice:true },
];

const GC_TASKS_EXTRA = [
  { id:'k4', title:'Собрать вечерний дайджест', who:'Аня', whoInit:'А', due:'Пятница, 19:00', prio:'Low', conf:76, source:'meeting', voice:false },
  { id:'k5', title:'Проверить daemon на Windows', who:'Дима', whoInit:'Д', due:'Завтра, 16:00', prio:'Medium', conf:84, source:'meeting', voice:true },
];

const GC_KANBAN = {
  Backlog: [
    { id:'b1', title:'Обновить onboarding daemon', who:'Аня', color:'#3da37a' },
    { id:'b2', title:'Документация workspace token', who:'Петя', color:'#3b82c4' },
  ],
  Todo: [
    { id:'td1', title:'Подготовить оплату', who:'Петя', color:'#3b82c4', risk:true },
    { id:'td2', title:'Проверить daemon на Windows', who:'Дима', color:'#d68b1c' },
  ],
  'In Progress': [
    { id:'ip1', title:'Поднять websocket для dashboard', who:'Дима', color:'#d68b1c' },
    { id:'ip2', title:'Интеграция с YouGile', who:'Аня', color:'#3da37a' },
  ],
  Review: [
    { id:'rv1', title:'Вечерний дайджест v2', who:'Аня', color:'#3da37a' },
  ],
  Done: [
    { id:'dn1', title:'Захват системного звука', who:'Дима', color:'#d68b1c' },
    { id:'dn2', title:'Telegram-подтверждения', who:'Петя', color:'#3b82c4' },
  ],
};

const GC_SIGNALS = [
  { id:'s1', kind:'risk', icon:'alert', title:'Риск обнаружен', desc:'Дедлайн оплаты завтра, задача все еще в Todo.', time:'2 мин назад' },
  { id:'s2', kind:'remind', icon:'bell', title:'Напоминание отправлено', desc:'Петя не обновлял статус задачи 2 дня.', time:'14 мин назад' },
  { id:'s3', kind:'create', icon:'checkCircle', title:'Карточка создана', desc:'Агент извлек задачу из реплики встречи.', time:'18 мин назад' },
];

const GC_TEAM = [
  { rank:'01', name:'Петя', xp:120, pct:100 },
  { rank:'02', name:'Аня', xp:95, pct:79 },
  { rank:'03', name:'Дима', xp:80, pct:67 },
];

const GC_CAPABILITIES = [
  { icon:'ear', title:'Захват встречи через daemon', desc:'Системный звук снимается на устройстве пользователя, без подключения сервера к звонку.' },
  { icon:'waves', title:'Распознавание договоренностей', desc:'Агент выделяет задачи, дедлайны, владельцев и контекст из живого разговора.' },
  { icon:'check', title:'Автоматическое создание задач', desc:'Реплика превращается в карточку со ссылкой на источник и уровнем уверенности.' },
  { icon:'users', title:'Назначение ответственных', desc:'Исполнитель определяется по контексту, голосу и роли участника в обсуждении.' },
  { icon:'send', title:'Telegram-подтверждения', desc:'Спорные задачи уходят на подтверждение исполнителю, а не тихо ломают процесс.' },
  { icon:'kanban', title:'Интеграция с канбан-доской', desc:'Колонки и статусы обновляются как зеркало реального проекта, а не отдельная копия.' },
  { icon:'bell', title:'Напоминания и дайджесты', desc:'Команда получает сводки и напоминания до того, как дедлайн становится пожаром.' },
  { icon:'alert', title:'Риски и просрочки', desc:'Grey Cardinal подсвечивает зависшие статусы, близкие дедлайны и потерянные задачи.' },
  { icon:'history', title:'История встреч и решений', desc:'Каждая задача связана с моментом разговора, где она появилась.' },
];

const GC_NAV = [
  { sec:'РАБОТА', items:[
    { id:'overview', icon:'grid', label:'Обзор' },
    { id:'meetings', icon:'ear', label:'Встречи', count:3 },
    { id:'tasks', icon:'list', label:'Задачи', count:12 },
    { id:'kanban', icon:'kanban', label:'Канбан' },
    { id:'risks', icon:'alert', label:'Риски', count:2 },
  ]},
  { sec:'КОМАНДА', items:[
    { id:'team', icon:'users', label:'Команда' },
    { id:'integrations', icon:'plug', label:'Интеграции' },
    { id:'daemon', icon:'server', label:'Daemon' },
  ]},
  { sec:'НАСТРОЙКИ', items:[
    { id:'settings', icon:'settings', label:'Настройки' },
  ]},
];

Object.assign(window, {
  GC_TRANSCRIPT, GC_TRANSCRIPT_EXTRA, GC_TASKS, GC_TASKS_EXTRA, GC_KANBAN,
  GC_SIGNALS, GC_TEAM, GC_CAPABILITIES, GC_NAV,
});

