export type OnboardingStep = {
  title: string;
  body: string;
  // Matches a nav link's data-tour-nav attribute in AppHeader — when the
  // link is visible, the tour highlights it instead of showing a plain
  // centered card, so the step visibly points at the tab it describes.
  navHref?: string;
};

const BASE_STEPS: OnboardingStep[] = [
  {
    title: "Добро пожаловать в Транскрибатор",
    body: "Сервис превращает аудио и видео в текст: загружаете запись — получаете транскрипт и краткую сводку. Дальше — коротко, что умеет каждая вкладка.",
  },
  {
    title: "Новая запись",
    body: "Перетащите файл в область загрузки или выберите его кликом. Есть два режима: «В фоне» — дешевле, готово в течение суток, и «Сейчас» — готово примерно за 30 минут по полной цене. Если связь оборвётся посреди загрузки, докачивание продолжится само.",
    navHref: "/",
  },
  {
    title: "Мои записи",
    body: "Список ваших записей со статусом и прогрессом обработки. У каждой — транскрипт, сводка, экспорт, вопросы к записи в Диалоге и возможность поделиться ссылкой. Отдельно показаны записи, которыми поделились с вами.",
    navHref: "/recordings",
  },
  {
    title: "Поддержка",
    body: "Нашли ошибку — опишите её и приложите скриншот (тоже можно перетащить). Заявка разбирается автоматически: проверяется несколько независимых версий причины, а не одна догадка, подтверждённая версия исправляется и выкатывается. Статус виден прямо в тикете.",
    navHref: "/tickets",
  },
  {
    title: "Профиль",
    body: "Здесь — данные аккаунта и удаление аккаунта, если оно понадобится.",
    navHref: "/profile",
  },
];

const ADMIN_STEP: OnboardingStep = {
  title: "Админка",
  body: "Доступна только администраторам: пользователи, все записи, логи ошибок, лог активности и тикеты поддержки — включая разбор гипотез по каждому тикету.",
  navHref: "/admin",
};

export function getOnboardingSteps(role: string): OnboardingStep[] {
  return role === "admin" ? [...BASE_STEPS, ADMIN_STEP] : BASE_STEPS;
}
