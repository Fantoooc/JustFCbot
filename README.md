## HideFCbot

Telegram bot to hide messages from others in public chats  
*Admins can check users who sends messages & who opens them to prevent spam requests.  
*Admins will not see your messages unless they are intended for them.

---

Usage:   
  
@hidefcbot
- (flags) userID or @username
- message or message_for_anyone if exc_flag
- text displayed in the message
- message_for_anyone or message if exc_flag

flags:
- exc_flag [!] - if you need to send message for anyone except user
- vis_flag [&] - if you want the recipient to see message for other(s)

Ex:
@hidefcbot !&@user message || this message is not for you
- @user will see: "this message is not for you"
- others will see:
  - Message for anyone: message
  - Message for @user: this message is not for you
  - Message id is: {message_key}

---

### ! Attention !
 - Author is an idiot
 - AI used
