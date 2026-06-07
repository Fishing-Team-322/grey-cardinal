// Зеркало grey_cardinal_contracts/telegram.py (подмножество, нужное frontend).

export interface TelegramChatInfo {
  id: number;
  type: string;
  title: string | null;
}

export interface TelegramMessageEvent {
  update_id: number;
  message_id: number;
  chat: TelegramChatInfo;
  sender: TelegramSender;
  text: string;
  date: string;
  message_thread_id: number | null;
  raw?: unknown;
}

export interface TelegramSender {
  id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
}

export type BotAction =
  | { type: "send_message"; chat_id: number; text: string; reply_markup?: unknown }
  | {
      type: "edit_message";
      chat_id: number;
      message_id: number;
      text: string;
      reply_markup?: unknown;
    }
  | { type: "answer_callback"; callback_query_id: string; text?: string; show_alert?: boolean };

export interface ActionsResponse {
  actions: BotAction[];
}
