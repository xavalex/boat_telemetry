<img width="513" height="440" alt="sbms_telegram" src="https://github.com/user-attachments/assets/c6c81e71-9752-44a9-afeb-3d2b24f7b0fd" />
I have set up a Raspberry Pi Zero W (about $45 on Amazon) with a Python script that is triggered by crontab every 15 minutes, collects data from the SBMS, then send it to a Telegram Bot I follow on my phone. It also collects data from a Victron SmartSolar mppt but that is not relevant here. See a copy of Telegram screen below.

The scipt is simple and can be found at https://github.com/xavalex/boat_telemetry. I used the /edata folder supplied by the SBMS web server. Thanks Dacian!

To create the bot :

1.Find @BotFather:Step 1.
Open Telegram and search for @BotFather in the search bar. Look for the official account, which has a blue verification checkmark next to the name. Beware of lookalike scam accounts.

2.Start the Chat:Step 2.
Click on @BotFather and press the Start button (or type /start) to initialize the bot. It will respond with a list of available commands.

3.Create a New Bot:Step 3.
Send the command /newbot. BotFather will ask you to choose a display name for your bot (e.g., My Testing Bot). This can be changed later.

4.Choose a Username:Step 4.
Next, you will be asked to choose a unique username for your bot. This username:

Must end strictly in bot (e.g., my_test_123_bot or TestBot).

Cannot contain special characters other than underscores.

Must be completely unique across Telegram.

5.Save Your API Token:Step 5.
Once a unique username is accepted, BotFather will send a success message containing your HTTP API Token (a long string of numbers and letters).

You must then connect to your bot and start the conversation with a "hello" or whatever. This gives it the permission to start sending messages.
