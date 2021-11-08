#!/usr/bin/python3


from argparse import ArgumentParser
from datetime import datetime
from json import load
from logging import INFO, basicConfig, getLogger
from subprocess import run
from sys import exit

from emoji import emojize
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (CallbackContext, CallbackQueryHandler,
                          CommandHandler, PicklePersistence, Updater)

from game import Game, RoundResult


def read_json(filename):
    """
    Read json file and exit if it not exist
    """
    try:
        with open(filename) as file:
            data = load(file)
        return data
    except FileNotFoundError:
        exit(f'File "{filename}"" does not exist')


def get_settings() -> tuple:
    """
    Read command lines arguments, return: specified config and token
    """
    parser = ArgumentParser(
        prog='Blackjack Telegram bot')
    parser.add_argument('-c', '--config', metavar='C',
                        help='config file name')
    parser.add_argument('-e', '--environment', metavar='E',
                        help='environment key')
    args = vars(parser.parse_args())
    conf = read_json(args['config'])
    env = args['environment']
    token = conf['token'][env]
    return conf, token


def log_event(update: Update, context: CallbackContext, event) -> None:
    """ For logging an event """
    user_id = update.effective_user.id
    try:
        username = context.bot_data['users'][user_id]['username']
        # Update user last active datetime
        context.bot_data['users'][user_id]['last_active'] = datetime.today()
    except KeyError:
        username = 'blackjack bot'
    log = f'{username} - {event}'
    logger.info(log)


def get_languages(config: dict) -> dict:
    """ Read languages, return: languages dict """
    messages = {}
    for lang in config['lang_files']:
        messages[lang] = read_json(config['lang_files'][lang])
    return messages


def start(update: Update, context: CallbackContext) -> None:
    """ Sends a welcome and also save user """
    language, _ = get_user_settings(context)
    txt_welcome = messages_txt[language]['txt_welcome']
    markup = get_keyboard(context, True, False, False, False, True)
    update.message.reply_text(txt_welcome, reply_markup=markup,
                              parse_mode='HTML')
    check_and_save_user(update, context)
    log_event(update, context, 'sent start')


def stop(update: Update, context: CallbackContext) -> None:
    """ Goodbye message and remove any user data """
    language, _ = get_user_settings(context)
    command = context.args
    if len(command) == 1 and command[0].lower() == 'yes':
        try:
            # Delete user's message or get an exception
            _, msg_status, msg_dealer, msg_player = (
                get_user_game_data(context))
            msg_status.delete()
            msg_dealer.delete()
            msg_player.delete()
            lm = 'sent stop with confirmation'
            log_event(update, context, lm)
            # Remove user data
            remove_user(update, context)
            txt_goodbye = messages_txt[language]['txt_goodbye']
            update.message.reply_text(txt_goodbye)
        except KeyError:
            txt_second_goodbye = messages_txt[language]['txt_second_goodbye']
            update.message.reply_text(txt_second_goodbye)
            lm = 'sent stop once again'
            log_event(update, context, lm)
    else:
        txt_stop = messages_txt[language]['txt_stop']
        update.effective_message.reply_text(txt_stop)
        log_event(update, context, 'sent stop')


def game(update: Update, context: CallbackContext) -> None:
    """ Handling callback for new or existing game """
    language, deck_count = get_user_settings(context)
    q_choice = messages_txt[language]['q_choice']
    b_start = messages_txt[language]['b_start']
    update.callback_query.answer(' - '.join([q_choice, b_start]))
    txt_game = ' '.join([emojize(':slot_machine:'),
                        messages_txt[language]['txt_game_start']])
    threshold = config['settings']['low_deck_threshold']
    dealer_hit_on = config['settings']['diller_hit_on']
    try:
        # If it works - it's a new game
        game, msg_status, msg_dealer, msg_player = get_user_game_data(context)
        # If user change deck count - we should make new game for him
        if game.deck_count != deck_count:
            game = Game(deck_count, threshold, dealer_hit_on)
            context.user_data['game'] = game
            log_event(update, context, 'new game - changed deck count')
        else:
            game.deal_cards()
            log_event(update, context, 'new game')
    except KeyError:
        # Set defaults for new game
        check_and_save_user(update, context)
        game = Game(deck_count, threshold, dealer_hit_on)
        context.user_data['game'] = game
        log_event(update, context, 'first game')
    context.user_data['in_game'] = True
    mtxt_dealer = make_hand_text(game.dealer_hand, True)
    mtxt_player = make_hand_text(game.player_hand, False)
    round_result = game.round_result
    markup = get_keyboard(context, False, True)
    if round_result.result == 'blackjack' and round_result.winner == 'player':
        # If player have a blackjack
        context.user_data['in_game'] = False
        markup = get_keyboard(context, True)
        mtxt_dealer = make_hand_text(game.dealer_hand, False)
        txt_game = process_round_result(update, context, round_result)
        log_event(update, context, 'got blackjack')
    try:
        # For fist game, messed up messages, etc...
        msg_status.edit_text(txt_game)
        msg_dealer.edit_text(mtxt_dealer)
        msg_player.edit_text(mtxt_player, reply_markup=markup)
    except (BadRequest, UnboundLocalError):
        msg_status = update.effective_message.reply_text(txt_game)
        msg_dealer = update.effective_message.reply_text(mtxt_dealer)
        msg_player = update.effective_message.reply_text(mtxt_player,
                                                         reply_markup=markup)
        log_event(update, context, 'first game or old keyboard')
        # Save messages we sent for editing later
        context.user_data['msg_status'] = msg_status
        context.user_data['msg_dealer'] = msg_dealer
        context.user_data['msg_player'] = msg_player


def hit(update: Update, context: CallbackContext) -> None:
    """ Handling callback player takes a card """
    language, _ = get_user_settings(context)
    q_choice = messages_txt[language]['q_choice']
    b_hit = messages_txt[language]['b_hit']
    update.callback_query.answer(' - '.join([q_choice, b_hit]))
    game, msg_status, _, msg_player = get_user_game_data(context)
    # Give card to player
    game.hit()
    log_event(update, context, 'take card')
    round_result = game.round_result
    mtxt_player = make_hand_text(game.player_hand, False)
    markup = get_keyboard(context)
    # Check for bust or blackjack
    if round_result.result == 'bust' or round_result.result == 'blackjack':
        msg_status.edit_text(process_round_result(
            update, context, round_result))
        context.user_data['in_game'] = False
        markup = get_keyboard(context, True)
    msg_player.edit_text(mtxt_player, reply_markup=markup)


def stand(update: Update, context: CallbackContext, from_double=False) -> None:
    """ Handling callback player stands """
    language, _ = get_user_settings(context)
    q_choice = messages_txt[language]['q_choice']
    b_stand = messages_txt[language]['b_stand']
    update.callback_query.answer(' - '.join([q_choice, b_stand]))
    game, msg_status, msg_dealer, msg_player = get_user_game_data(context)
    # Game event - it's dealer's turn now
    game.stand()
    log_event(update, context, 'stand')
    round_result = game.round_result
    mtxt_dealer = make_hand_text(game.dealer_hand, False)
    mtxt_player = make_hand_text(game.player_hand, False)
    if round_result.result == 'blackjack' and round_result.winner == 'dealer':
        # If dealer have a blackjack - we should show his hand
        mtxt_dealer = make_hand_text(game.dealer_hand, False)
    # If player doubles earlier
    if from_double:
        txt_res = process_round_result(update, context, round_result, True)
    else:
        txt_res = process_round_result(update, context, round_result)
    msg_status.edit_text(txt_res)
    context.user_data['in_game'] = False
    markup = get_keyboard(context, True)
    msg_dealer.edit_text(mtxt_dealer)
    msg_player.edit_text(mtxt_player, reply_markup=markup)


def double(update: Update, context: CallbackContext) -> None:
    """ Handling callback player doubles """
    language, _ = get_user_settings(context)
    q_choice = messages_txt[language]['q_choice']
    b_double = messages_txt[language]['b_double']
    update.callback_query.answer(' - '.join([q_choice, b_double]))
    game, msg_status, _, msg_player = get_user_game_data(context)
    # Giving user a card
    game.hit()
    log_event(update, context, 'double')
    round_result = game.round_result
    mtxt_player = make_hand_text(game.player_hand, False)
    # Do not remove the keyboard
    markup = get_keyboard(context, False, True)
    msg_player.edit_text(mtxt_player, reply_markup=markup)
    # Check that it's not bust
    if round_result.result == 'bust':
        context.user_data['in_game'] = False
        markup = get_keyboard(context, True)
        msg_player.edit_text(mtxt_player, reply_markup=markup)
        msg_status.edit_text(process_round_result(
            update, context, round_result, True))
    else:
        # Now it's dealers' turn
        stand(update, context, True)


def get_keyboard(context: CallbackContext, new_game=False, double=False,
                 bet_set=False, settings=False,
                 start_message=False) -> InlineKeyboardMarkup:
    """
    Making game keyboard

    Options are:
        new_game - with game button,
        double - with double button,
        bet_set - keys for bet set menu,
        start_message - only new game button (for first message)

    Return: InlineKeyboardMarkup
    """
    language, deck_count = get_user_settings(context)
    bet, balance = get_user_bet_and_balance(context)
    # Making first row of keyboard
    if new_game:
        # For new game
        b_start = ' '.join([emojize(':game_die:'),
                            messages_txt[language]['b_start']])
        keyboard_row_1 = []
        keyboard_row_1.append(InlineKeyboardButton(b_start,
                                                   callback_data='game'))
        keyboard = [keyboard_row_1]
    elif bet_set:
        # For bet set menu
        keyboard_row_1 = []
        keyboard_row_1.append(InlineKeyboardButton(
            emojize(':downwards_button:'), callback_data='bet.decrease'))
        keyboard_row_1.append(InlineKeyboardButton(
            emojize(':upwards_button:'), callback_data='bet.increase'))
    elif settings:
        # For settings menu
        b_rating = ' '.join([emojize(':trophy:'),
                            messages_txt[language]['b_rating']])
        b_language = ' '.join([emojize(':input_latin_uppercase:'),
                              messages_txt[language]['b_language']])
        b_language_caption = messages_txt[language]['b_language_caption']
        b_deck_count = ' '.join([emojize(':input_numbers:'),
                                messages_txt[language]['b_deck_count']])
        b_reset = ' '.join([emojize(':money_bag:'),
                            messages_txt[language]['b_reset']])
        keyboard_row_1 = []
        keyboard_row_1.append([InlineKeyboardButton(
            b_rating, callback_data='settings.rating')])
        keyboard_row_1.append([InlineKeyboardButton(
            ': '.join([b_language, b_language_caption]),
            callback_data='settings.language')])
        keyboard_row_1.append([InlineKeyboardButton(
            ': '.join([b_deck_count, str(deck_count)]),
            callback_data='settings.deck_count')])
        keyboard_row_1.append([InlineKeyboardButton(
            b_reset, callback_data='settings.balance_reset')])
    else:
        # Making ingame buttons
        b_hit = ' '.join([emojize(':backhand_index_pointing_down:'),
                         messages_txt[language]['b_hit']])
        b_stand = ' '.join([emojize(':raised_hand:'),
                           messages_txt[language]['b_stand']])
        b_double = ' '.join([emojize(':victory_hand:'),
                            messages_txt[language]['b_double']])
        keyboard_row_1 = []
        keyboard_row_1.append(InlineKeyboardButton(b_hit, callback_data='hit'))
        keyboard_row_1.append(InlineKeyboardButton(b_stand,
                                                   callback_data='stand'))
        if double:
            keyboard_row_1.append(InlineKeyboardButton(b_double,
                                                       callback_data='double'))
    # Making last row of keyboard
    bet = ' '.join([emojize(':dollar_banknote:'), str(bet),
                   '[' + str(balance - bet) + ']'])
    b_settings = ' '.join([emojize(':gear:'),
                          messages_txt[language]['b_settings']])
    keyboard_row_2 = []
    keyboard_row_2.append(InlineKeyboardButton(bet, callback_data='bet'))
    keyboard_row_2.append(InlineKeyboardButton(b_settings,
                                               callback_data='settings'))
    keyboard = [keyboard_row_1, keyboard_row_2]
    # For very first game
    if start_message:
        keyboard = [keyboard_row_1]
    # Different layout for settings menu
    if settings:
        keyboard = keyboard_row_1 + [keyboard_row_2]
    markup = InlineKeyboardMarkup(keyboard)
    return markup


def make_hand_text(hand: list, hidden: bool) -> str:
    """ Returns hand text """
    text = ''
    for num, card in enumerate(hand):
        if hidden and num > 0:
            text = text
        else:
            text = text + str(card[0]) + ' ' + card[1] + '  '
    # Remove of space in the end
    return text.strip()


def process_round_result(update: Update, context: CallbackContext,
                         result: RoundResult, double=False) -> str:
    """
    Round result processing, count score and return status message
    """
    language, _ = get_user_settings(context)
    org_bet, balance = get_user_bet_and_balance(context)
    # All actions with temporary bet, because we save original bet later
    bet = org_bet
    if double:
        bet = bet * 2
    txt_win = messages_txt[language]['txt_win']
    txt_lose = messages_txt[language]['txt_lose']
    txt_blackjack = messages_txt[language]['txt_blackjack']
    txt_bust = messages_txt[language]['txt_bust']
    txt_tie = messages_txt[language]['txt_tie']
    # Only for log - player don't see this
    txt_forfeit = 'forfeit'
    state_text = []
    if result.result == 'tie':
        state_text.append(' '.join([emojize(':raised_fist:'), txt_tie]))
    else:
        if result.winner == 'player':
            state_text.append(' '.join([emojize(':thumbs_up:'), txt_win]))
            if result.result == 'blackjack':
                state_text.append(txt_blackjack)
                bet = int(bet * 1.5)
            elif result.result == 'bust':
                state_text.append(txt_bust)
            balance = balance + bet
            update_total(update, context, bet)
        elif result.winner == 'dealer':
            state_text.append(' '.join([emojize(':thumbs_down:'), txt_lose]))
            if result.result == 'blackjack':
                state_text.append(txt_blackjack)
            elif result.result == 'bust':
                state_text.append(txt_bust)
            elif result.result == 'forfeit':
                # Only for log - player don't see this
                state_text.append(txt_forfeit)
            balance = balance - bet
            update_total(update, context, bet * -1)
        set_user_bet_and_balance(context, org_bet, balance)
    if len(state_text) == 1:
        state_text = state_text[0]
    else:
        state_text = ' - '.join(state_text)
    log_event(update, context, f'{state_text}, bet: {bet}')
    return state_text


def bet(update: Update, context: CallbackContext) -> None:
    """ Handling callback for bet set menu """
    data = update.callback_query.data
    bet, balance = get_user_bet_and_balance(context)
    language, _ = get_user_settings(context)
    _, msg_status, msg_dealer, msg_player = get_user_game_data(context)
    q_choice = messages_txt[language]['q_choice']
    q_bet_increase = messages_txt[language]['q_bet_increase']
    q_bet_decrease = messages_txt[language]['q_bet_decrease']
    q_bet_confirm = messages_txt[language]['q_bet_confirm']
    q_bet_warn = messages_txt[language]['q_bet_warn']
    txt_m_bet_title = messages_txt[language]['txt_m_bet_title']
    txt_m_bet_game = ' '.join([emojize(':dollar_banknote:'),
                               txt_m_bet_title])
    txt_m_bet_hint = ' '.join([messages_txt[language]['txt_m_bet_hint'] +
                               ':', str(config['settings']['min_bet']), '-',
                               str(config['settings']['max_bet'])])
    txt_m_bet_title_confirm = messages_txt[language]['txt_m_bet_title_confirm']
    txt_m_bet_title_confirm_game = ' '.join([emojize(':check_mark_button:'),
                                            txt_m_bet_title_confirm])
    txt_m_goodluck = messages_txt[language]['txt_m_goodluck']
    txt_m_bet = messages_txt[language]['txt_m_bet']
    txt_bet_value = ': '.join([txt_m_bet, str(bet)])
    markup = get_keyboard(context, False, False, True)
    # Player lose bet if game is active
    if context.user_data['in_game']:
        context.user_data['in_game'] = False
        result = RoundResult
        result.result = 'forfeit'
        result.winner = 'dealer'
        process_round_result(update, context, result)
    if data == 'bet':
        # Try to figure are we open or close that menu
        user_in_menu = context.user_data.get('is_in_bet_menu', True)
        # If player go from one menu to another
        context.user_data['is_in_settings_menu'] = True
        if user_in_menu:
            update.callback_query.answer(' - '.join([q_choice,
                                                    txt_m_bet_title]))
            context.user_data['is_in_bet_menu'] = False
            msg_status.edit_text(txt_m_bet_game)
            msg_dealer.edit_text(txt_m_bet_hint)
            msg_player.edit_text(txt_bet_value, reply_markup=markup)
            log_event(update, context, 'opens bet set menu')
        else:
            update.callback_query.answer(' - '.join([q_choice, q_bet_confirm]))
            context.user_data['is_in_bet_menu'] = True
            msg_status.edit_text(txt_m_bet_title_confirm_game)
            msg_dealer.edit_text(txt_m_goodluck)
            context.user_data['in_game'] = False
            markup = get_keyboard(context, True)
            msg_player.edit_reply_markup(markup)
            log_event(update, context, 'exits bet set menu')
    else:
        # For menu buttons
        bet_action = data.split('.')[1]
        if bet_action == 'increase' and bet < config['settings']['max_bet']:
            bet = bet + 2
            update.callback_query.answer(' - '.join([q_choice,
                                                     q_bet_increase]))
            log_event(update, context, f'increased bet: {bet}')
        elif bet_action == 'decrease' and bet > config['settings']['min_bet']:
            bet = bet - 2
            update.callback_query.answer(' - '.join([q_choice,
                                                     q_bet_decrease]))
            log_event(update, context, f'decreased bet: {bet}')
        else:
            update.callback_query.answer(q_bet_warn)
            log_event(update, context, 'get to bet limit')
        set_user_bet_and_balance(context, bet, balance)
        txt_bet = ': '.join([txt_m_bet, str(bet)])
        markup = get_keyboard(context, False, False, True)
        try:
            msg_player.edit_text(txt_bet, reply_markup=markup)
        except BadRequest:
            # For playes keep pressing buttons after limit
            pass


def settings(update: Update, context: CallbackContext) -> None:
    """ Handling callback for settings menu """
    data = update.callback_query.data
    language, deck_count = get_user_settings(context)
    _, msg_status, msg_dealer, msg_player = get_user_game_data(context)
    q_choice = messages_txt[language]['q_choice']
    q_sett_confirm = messages_txt[language]['q_sett_confirm']
    q_sett_lang = messages_txt[language]['q_sett_lang']
    q_sett_deck_c = messages_txt[language]['q_sett_deck_c']
    q_sett_bal_reset = messages_txt[language]['q_sett_bal_reset']
    txt_m_sett_title = messages_txt[language]['txt_m_sett_title']
    txt_m_sett_title_game = ' '.join([emojize(':gear:'), txt_m_sett_title])
    txt_m_sett_hint = messages_txt[language]['txt_m_sett_hint']
    txt_m_sett_title_confirm = (
        messages_txt[language]['txt_m_sett_title_confirm'])
    txt_m_sett_title_confirm_game = ' '.join([emojize(':check_mark_button:'),
                                             txt_m_sett_title_confirm])
    txt_m_goodluck = messages_txt[language]['txt_m_goodluck']
    txt_m_sett_b_reset = messages_txt[language]['txt_m_sett_b_reset']
    txt_m_place = messages_txt[language]['txt_m_place']
    txt_m_from = messages_txt[language]['txt_m_from']
    b_deck_count = messages_txt[language]['b_deck_count']
    b_rating = messages_txt[language]['b_rating']
    b_rating_game = ' '.join([emojize(':trophy:'), b_rating])
    markup = get_keyboard(context, False, False, False, True)
    # Player lose bet if game is active
    if context.user_data['in_game']:
        context.user_data['in_game'] = False
        result = RoundResult
        result.result = 'forfeit'
        result.winner = 'dealer'
        process_round_result(update, context, result)
    if data == 'settings':
        # Try to figure are we open or close that menu
        user_in_menu = context.user_data.get('is_in_settings_menu', True)
        # If player go from one menu to another
        context.user_data['is_in_bet_menu'] = True
        if user_in_menu:
            update.callback_query.answer(' - '.join([q_choice,
                                                    txt_m_sett_title]))
            context.user_data['is_in_settings_menu'] = False
            msg_status.edit_text(txt_m_sett_title_game)
            msg_dealer.edit_text(txt_m_sett_hint)
            msg_player.edit_text('---', reply_markup=markup)
            log_event(update, context, 'opens settings menu')
        else:
            update.callback_query.answer(' - '.join([q_choice,
                                                    q_sett_confirm]))
            context.user_data['is_in_settings_menu'] = True
            msg_status.edit_text(txt_m_sett_title_confirm_game)
            msg_dealer.edit_text(txt_m_goodluck)
            context.user_data['in_game'] = False
            markup = get_keyboard(context, True)
            msg_player.edit_reply_markup(markup)
            log_event(update, context, 'exits settings menu')
    else:
        # For menu buttons
        setting = data.split('.')[1]
        if setting == 'language':
            if language == 'ru':
                context.user_data['language'] = 'en'
            else:
                context.user_data['language'] = 'ru'
            # Get new language for callback query answer
            language, _ = get_user_settings(context)
            b_language = messages_txt[language]['b_language']
            b_language_caption = messages_txt[language]['b_language_caption']
            txt_lang = ': '.join([b_language, b_language_caption])
            q_choice = messages_txt[language]['q_choice']
            update.callback_query.answer(' - '.join([q_choice, q_sett_lang]))
            msg_dealer.edit_text(txt_lang)
            log_event(update, context, f'changes language: {language}')
        elif setting == 'deck_count':
            if deck_count < 8:
                context.user_data['deck_count'] = deck_count + 1
            else:
                context.user_data['deck_count'] = 1
            # Get deck count for proper visualisation
            _, deck_count = get_user_settings(context)
            txt_deck_count = ': '.join([b_deck_count, str(deck_count)])
            update.callback_query.answer(' - '.join([q_choice, q_sett_deck_c]))
            msg_dealer.edit_text(txt_deck_count)
            lm = f'changed deck count: {deck_count}'
            log_event(update, context, lm)
        elif setting == 'balance_reset':
            # We can erase it - there will be defaults
            context.user_data.pop('bet', None)
            context.user_data.pop('balance', None)
            update.callback_query.answer(' - '.join([q_choice,
                                                    q_sett_bal_reset]))
            log_event(update, context, 'resets balance')
            try:
                # For players keep pressing button
                msg_dealer.edit_text(txt_m_sett_b_reset)
            except BadRequest:
                pass
        elif setting == 'rating':
            update.callback_query.answer(' - '.join([q_choice,
                                                    b_rating]))
            txt_rating = make_rating_text(context)
            txt_rating = b_rating_game + 2 * '\n' + txt_rating
            user_id = update.effective_user.id
            place = context.bot_data['rating'][user_id]['place']
            places_total = context.bot_data['rating'][user_id]['places_total']
            txt_user_rating = ' '.join([txt_m_place + ':', str(place),
                                       txt_m_from, str(places_total)])
            log_event(update, context, 'asks for rating')
            try:
                # For players keep pressing button
                msg_dealer.edit_text(txt_rating)
                # Do not remove keyboard for smoooth visualisation
                msg_player.edit_text(txt_user_rating, reply_markup=markup)
            except BadRequest:
                pass
        markup = get_keyboard(context, False, False, False, True)
        try:
            msg_player.edit_reply_markup(markup)
        except BadRequest:
            # For players keep pressing button
            pass


def get_user_settings(context: CallbackContext) -> tuple:
    """
    For getting user setting or defaults, if user doesn't set any

    Returns:
        language - user's interface language,
        deck_count - user's deck count
     """
    defaults = config['defaults']
    language = context.user_data.get('language', defaults['language'])
    deck_count = context.user_data.get('deck_count', defaults['deck_count'])
    return language, deck_count


def get_user_bet_and_balance(context: CallbackContext) -> tuple:
    """ For getting user bet and balance, returns: bet, balance """
    defaults = config['defaults']
    bet = context.user_data.get('bet', defaults['bet'])
    balance = context.user_data.get('balance', defaults['balance'])
    return bet, balance


def set_user_bet_and_balance(context: CallbackContext, bet, balance) -> None:
    """ For saving user's bet and balance """
    context.user_data['bet'] = bet
    context.user_data['balance'] = balance


def update_total(update: Update, context: CallbackContext, delta: int) -> None:
    """ For counting accumulated total """
    user_id = update.effective_user.id
    # If it's very first entry
    context.bot_data['total'] = context.bot_data.get('total', {})
    total = context.bot_data['total']
    # If it's very first entry for user
    total[user_id] = total.get(user_id, 0) + delta


def make_rating_text(context: CallbackContext) -> str:
    """ Make scoreboard text, return this text """
    users = context.bot_data['users']
    total = context.bot_data['total']
    board = []
    for item in total:
        board.append((users[item]['username'], total[item], item))
    board.sort(key=lambda tup: tup[1], reverse=True)
    places_total = len(board)
    # If it's very first entry
    context.bot_data['rating'] = context.bot_data.get('rating', {})
    board_txt = ''
    for num, board_entry in enumerate(board):
        # Let's count like humans do
        num += 1
        username, score, chat_id = board_entry
        # If it's very first entry for user
        context.bot_data['rating'][chat_id] = (
            context.bot_data['rating'].get(chat_id, {}))
        user_rating = context.bot_data['rating']
        user_rating[chat_id]['place'] = num
        user_rating[chat_id]['places_total'] = places_total
        # Limit the top
        if num <= config['settings']['rating_places']:
            if num == 1:
                num = emojize(':1st_place_medal:')
            elif num == 2:
                num = emojize(':2nd_place_medal:')
            elif num == 3:
                num = emojize(':3rd_place_medal:')
            else:
                num = f'{num:02d} '
            board_txt = board_txt + ' '.join([num, username, ' ',
                                             str(score)]) + '\n'
        else:
            pass
    # Remove space in the end
    return board_txt.split()


def get_user_game_data(context: CallbackContext) -> tuple:
    """
    Get user's game state

    Returns:
        msg_status - first message,
        msg_dealer - middle message,
        msg_player - last message
     """
    game = context.user_data['game']
    msg_status = context.user_data['msg_status']
    msg_dealer = context.user_data['msg_dealer']
    msg_player = context.user_data['msg_player']
    return game, msg_status, msg_dealer, msg_player


def check_and_save_user(update: Update, context: CallbackContext) -> None:
    """ Save user date if it's not saved already """
    user_id = update.effective_user.id
    if update.effective_user.full_name is None:
        username = update.effective_user.username
    else:
        username = update.effective_user.full_name
    # If it's very first user
    context.bot_data['users'] = context.bot_data.get('users', {})
    users = context.bot_data['users']
    if user_id not in users:
        users[user_id] = {}
        users[user_id]['username'] = username
        users[user_id]['language_code'] = update.effective_user.language_code
        lm = f'added user: {user_id}, {username}'
        log_event(update, context, lm)


def remove_user(update: Update, context: CallbackContext) -> None:
    """ Remove user from scoreboard and all data """
    user_id = update.effective_user.id
    # Remove all temp user data
    context.user_data.clear()
    # Remove user from user rating and mail list
    for d in context.bot_data:
        context.bot_data[d].pop(user_id, None)
    log_event(update, context, f'removed user: {user_id}')


def announce(update: Update, context: CallbackContext) -> None:
    """ Secret command for bulk messaging """
    if update.effective_message.chat_id != config['owner_id']:
        lm = "sent announce, but it's a secret command!"
        log_event(update, context, lm)
    else:
        if len(context.args) == 0:
            # If no arguments was specified
            log_event(update, context, 'sent announce without arguments')
        elif len(context.args) != 0:
            command = context.args
            lang_code = None
            # If command was with language code
            if command[0].lower() == 'ru' or command[0].lower() == 'en':
                lang_code = command[0].lower()
                command.pop(0)
            msg = ' '.join(command)
            users = context.bot_data['users']
            count = 0
            for user in users:
                # If command was with language code
                if lang_code is not None:
                    lm = f'sent announce for language {lang_code}'
                    log_event(update, context, lm)
                    if users[user]['language_code'] == lang_code:
                        update.effective_message.bot.send_message(
                            chat_id=user, text=msg)
                else:
                    lm = 'sent announce for all'
                    log_event(update, context, lm)
                    update.effective_message.bot.send_message(
                        chat_id=user, text=msg)
                count += 1
                lm = (f'sent message "{msg}" to user {user},' +
                      f' total sent {count} messages')
                log_event(update, context, lm)


def logs(update: Update, context: CallbackContext) -> None:
    """ Secret command for getting logs """
    if update.effective_message.chat_id != config['owner_id']:
        lm = "sent logs, but it's a secret command!"
        log_event(update, context, lm)
    else:
        if len(context.args) == 0:
            log_count = str(config['logging']['log_length'])
            lm = f'sent logs without arguments, {log_count} taken'
            log_event(update, context, lm)
        elif len(context.args) == 1:
            log_count = context.args[0]
            log_event(update, context, f'sent logs with {log_count} lentg')
        else:
            lm = 'sent logs with improper arguments'
            log_event(update, context, lm)
        result = run(['tail', '-n', log_count, log_file],
                     capture_output=True, universal_newlines=True)
        log = result.stdout
        if len(log) > 4096:
            for x in range(0, len(log), 4096):
                update.message.reply_text(log[x:x+4096])
        else:
            update.message.reply_text(log)


def usersinfo(update: Update, context: CallbackContext) -> None:
    """ Secret command for getting user details and activity status """
    if update.effective_message.chat_id != config['owner_id']:
        lm = "sent users, but it's a secret command!"
        log_event(update, context, lm)
    else:
        users = context.bot_data['users']
        playersinfo = []
        for user in users:
            try:
                place = str(context.bot_data['rating'][user]['place'])
                total = str(context.bot_data['total'][user])
            except KeyError:
                place = '-'
                total = '-'
            user = users[user]
            username = user['username']
            language_code = user['language_code']
            last_active = user['last_active'].isoformat(sep=' ',
                                                        timespec='minutes')
            playersinfo.append((username, language_code, last_active,
                                place, total))
        playersinfo.sort(key=lambda tup: tup[3])
        infotext = ''
        for player in playersinfo:
            username, language_code, last_active, place, total = player
            infotext = infotext + ' '.join([username, language_code, '\n'])
            infotext = infotext + ' '.join([last_active, '#' + place,
                                           'Score: ' + total, 2 * '\n'])
        infotext = infotext[:-2]
        if len(infotext) > 4096:
            for x in range(0, len(infotext), 4096):
                update.message.reply_text(infotext[x:x+4096])
        else:
            update.message.reply_text(infotext)
        log_event(update, context, 'sent users')


def main(token: str) -> None:
    """ Start a bot with handlers """
    updater = Updater(token, persistence=datafile)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('stop', stop, pass_args=True))
    # Adding handlers
    dispatcher.add_handler(CallbackQueryHandler(game, pattern='game'))
    dispatcher.add_handler(CallbackQueryHandler(hit, pattern='hit'))
    dispatcher.add_handler(CallbackQueryHandler(stand, pattern='stand'))
    dispatcher.add_handler(CallbackQueryHandler(double, pattern='double'))
    dispatcher.add_handler(CallbackQueryHandler(bet, pattern='bet*'))
    dispatcher.add_handler(CallbackQueryHandler(settings, pattern='settings*'))
    # Secret commands
    dispatcher.add_handler(CommandHandler('announce',
                                          announce, pass_args=True))
    dispatcher.add_handler(CommandHandler('logs',
                                          logs, pass_args=True))
    dispatcher.add_handler(CommandHandler('users', usersinfo))
    updater.start_polling(drop_pending_updates=True)
    updater.idle()


# Get configuration and token
config, token = get_settings()
messages_txt = get_languages(config)

# Logs
log_file = config['logging']['log_file']
log_format = '%(asctime)s %(levelname)s %(name)s %(message)s'
basicConfig(filename=log_file, format=log_format, level=INFO)
logger = getLogger(__name__)

# Persistance
data_filename = config['persistence']['data_file']
datafile = PicklePersistence(filename=data_filename)

# Working until we get a SIGNAL
if __name__ == '__main__':
    main(token)
