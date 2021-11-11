# PyBlackjackBot Blackjack bot for Telegram

Simple telegram bot on python3 with inline keyboards and user scoreboard. 

This bot uses the [python telegram bot](https://python-telegram-bot.org) framework to make Telegram API calls.

My goal was to test the possibility of creating a telegram bot that does not send messages to the user, but only edits ones that it has previously sent in addition with using inline keyboards.

You can see this bot in action here: https://t.me/blackjack_gamebot.

## Installation

### Install 

It's really simple just do following steps to run from source (you need python3 & token from your bot), you need to specify your _bot token_ in config file.
1. `git clone https://github.com/GarikFirst/PyBlackjackBot.git` - clone this repo.
2. `pip3 install -r requirments.txt` - install requirments.
3. specify your bot _token_ in **token** key in `config.json`.
4. specify your bot _user id_ in **bot_owner** tag in `config.json`, if you'd like to use secret commands.

### Launch the bot

1. `python 3 -c CONFIG-FILE -e YOUR-ENV-FROM-CONFIG` - defaults (no keys specified) are **config.json** and **dev** accoringly
2. go and check your bot in Telegram client by sending /start

## Secret commands

This bot has several secret command, wich can be sent to bot by owner and help you get some info about playes current activities. Just make shure you specify your _user id_ in config earlier on installation steps.

- `/logs n` (n can be ommited) - return n lines from logfile, if n is ommited, than **log_length** from config file number of lines
- `/users` - return information about users, they scores and last activity time
- `/announce language_code text`, (language_code, **ru**/**en**, can be ommited) - bulk send message with 'text' to all users with specified language code, if code is ommited - to all users

## Config options

| Option                   | Description                                                 |
| ------------------------ | ------------------------------------------------------------|
| **system options**                                                                     |
| owner_id                 | telegram user id of owner                                   |
| **default game user settings**                                                         |
| balance                  | user's start balance                                        |
| bet                      | user's initial bet                                          |
| deck_count               | user's number of decks                                      |
| language                 | user's interface language                                   |
| **language files**                                                                     |
| language_code            | filename for that language code                             |
| **logging**                                                                            |
| log_file                 | filename for logfile                                        |
| log_length               | default log length for `/logs` command                      |
| persistence                                                                            |
| data_file                | filename for persistance picle file                         |
| **game settings**                                                                      |
| diller_hit_on            | score count when diller shouldn' hit                        | 
| low_deck_threshold       | float, percent of card in deck when deck should be shuffled |
| max_bet       | maximum bet limit                                                      |
| min_bet | maximum bet limit                                                            |
| rating_places | how much lines will be in scoreboard                                   |
| **token**                                                                              |
| environment key | token for that environment                                           |

Copyright © 2021 Igor Bulekov
