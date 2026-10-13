// 由 scripts/build_demo_data.py 產生：實際執行 labs/intermediate 的紀錄（FakeLLM，問題：我今年還剩幾天特休？）
window.FDE_TOOL_TRACE = [
 {
  "kind": "request",
  "messages": [
   {
    "role": "user",
    "content": "<手冊>\n[H01] 特休假：到職滿六個月後享有三天特休；滿一年七天；滿二年十天；滿三年十四天；滿五年十五天。 請特休需在三個工作天前於人事系統提出申請，由直屬主管核准。當年度未休完的特休，可遞延至次年度六月底前使用。\n</手冊>\n\n問題：我今年還剩幾天特休？"
   }
  ],
  "tools": [
   "get_leave_balance",
   "get_today"
  ]
 },
 {
  "kind": "reply",
  "stop_reason": "tool_use",
  "content": [
   {
    "type": "tool_use",
    "id": "toolu_fake_1",
    "name": "get_leave_balance",
    "input": {}
   }
  ]
 },
 {
  "kind": "request",
  "messages": [
   {
    "role": "user",
    "content": "<手冊>\n[H01] 特休假：到職滿六個月後享有三天特休；滿一年七天；滿二年十天；滿三年十四天；滿五年十五天。 請特休需在三個工作天前於人事系統提出申請，由直屬主管核准。當年度未休完的特休，可遞延至次年度六月底前使用。\n</手冊>\n\n問題：我今年還剩幾天特休？"
   },
   {
    "role": "assistant",
    "content": [
     {
      "type": "tool_use",
      "id": "toolu_fake_1",
      "name": "get_leave_balance",
      "input": {}
     }
    ]
   },
   {
    "role": "user",
    "content": [
     {
      "type": "tool_result",
      "tool_use_id": "toolu_fake_1",
      "content": "{\"total\": 10, \"used\": 6, \"remaining\": 4}",
      "is_error": false
     }
    ]
   }
  ],
  "tools": [
   "get_leave_balance",
   "get_today"
  ]
 },
 {
  "kind": "reply",
  "stop_reason": "end_turn",
  "content": [
   {
    "type": "text",
    "text": "{\"found\": true, \"answer\": \"你今年還剩 4 天特休（共 10 天，已休 6 天）。\", \"citations\": [\"H01\"]}"
   }
  ]
 },
 {
  "kind": "final",
  "answer": {
   "found": true,
   "answer": "你今年還剩 4 天特休（共 10 天，已休 6 天）。",
   "citations": [
    "H01"
   ]
  }
 }
];
