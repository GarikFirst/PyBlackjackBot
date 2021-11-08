from random import shuffle

from emoji import emojize


class RoundResult:
    """
    Representation of the round result

    Contains:
        result: result of the round,
        winner: who win the round

    Valid results: None, tie, blackjack, bust, score
    Valid winners: None, dealer, player

    The outcome of the game must be determined by a combination of
    result and winner

    If result is bust - winner is always the opposite side
    """
    def __init__(self) -> None:
        self.__result = None
        self.__winner = None

    @property
    def result(self):
        return self.__result

    @result.setter
    def result(self, value):
        if value in ['blackjack', 'tie', 'bust', 'score', 'forfeit']:
            self.__result = value
        else:
            raise ValueError

    @property
    def winner(self):
        return self.__winner

    @winner.setter
    def winner(self, value):
        if value in ['dealer', 'player']:
            self.__winner = value
        else:
            raise ValueError


class Game:
    """ Game mechanics """
    def __init__(self, deck_count: int, low_deck_threshold: float,
                 diller_hit_on: int) -> None:
        self.__make_deck(deck_count)
        self.__deck_size = deck_count
        self.__low_deck_threshold = low_deck_threshold
        self.__diller_hit_on = diller_hit_on
        self.__dealer_hand = []
        self.__player_hand = []
        # Deal two cards at the beginning of the game
        self.deal_cards()

    @property
    def dealer_hand(self):
        return self.__dealer_hand

    @property
    def player_hand(self):
        return self.__player_hand

    @property
    def deck_count(self):
        return self.__deck_size

    @property
    def round_result(self):
        return self.__get_round_result()

    def __make_deck(self, deck_count: int) -> None:
        """ Create deck from target number of decks """
        cards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 'J', 'Q', 'K', 'A']
        suits = list(map(emojize, [':spade_suit:', ':diamond_suit:',
                                   ':club_suit:', ':heart_suit:']))
        deck = []
        while deck_count > 0:
            deck_count -= 1
            for suit in suits:
                for card in cards:
                    deck.append((card, suit))
        shuffle(deck)
        self.__deck = deck

    def __check_and_remake_deck(self) -> None:
        """ Shuffle the deck if target card count below threshold """
        if (len(self.__deck) < 52 * self.__deck_size *
           self.__low_deck_threshold):
            self.__make_deck(self.__deck_size)

    def __take_card(self, hand: list) -> None:
        """ Put a card in target hand and remove from deck """
        hand = hand.append(self.__deck[0])
        self.__deck.pop(0)
        # Check if there is enough cards in deck
        self.__check_and_remake_deck()

    def deal_cards(self) -> None:
        """
        Deal two cards for dealer and player in
        the beginning of the round
        """
        self.__dealer_hand.clear()
        self.__player_hand.clear()
        for i in range(2):
            self.__take_card(self.__dealer_hand)
            self.__take_card(self.__player_hand)

    def __count_cards(self, hand: list) -> int:
        """ Card score count """
        # We should place aces at the end of the list
        tmp_hand = sorted(hand, key=str, reverse=True)
        count = 0
        for card in tmp_hand:
            value = card[0]
            if isinstance(value, int):
                count = count + value
            elif value != 'A':
                count = count + 10
            else:
                if count <= 10:
                    count = count + 11
                else:
                    count = count + 1
        return count

    def hit(self) -> None:
        """ Player takes a card """
        self.__take_card(self.player_hand)

    def stand(self) -> None:
        """ Player hold and pass game to dealer """
        while self.__make_diller_desicion():
            self.__take_card(self.dealer_hand)

    def __make_diller_desicion(self) -> bool:
        """ Dealer descision making """
        score = self.__count_cards(self.dealer_hand)
        if score <= self.__diller_hit_on:
            return True
        else:
            return False

    def __get_round_result(self) -> RoundResult:
        """ Return game state after a round """
        result = RoundResult()
        d_score = self.__count_cards(self.__dealer_hand)
        p_score = self.__count_cards(self.__player_hand)
        d_card_count = len(self.__dealer_hand)
        p_card_count = len(self.__player_hand)
        if (p_score == 21 and p_card_count == 2 and
           self.__dealer_hand[0][0] not in [10, 'J', 'Q', 'K', 'A']):
            result.result = 'blackjack'
            result.winner = 'player'
        elif (d_score == 21 and d_card_count == 2 and
              p_score == 21 and p_card_count == 2):
            result.result = 'tie'
        elif d_score == 21 and d_card_count == 2:
            result.result = 'blackjack'
            result.winner = 'dealer'
        elif d_score > 21:
            result.result = 'bust'
            result.winner = 'player'
        elif d_score > 21:
            result.result = 'bust'
            result.winner = 'player'
        elif p_score > 21:
            result.result = 'bust'
            result.winner = 'dealer'
        # Score counting after all special conditions
        elif d_score > p_score:
            result.result = 'score'
            result.winner = 'dealer'
        elif p_score > d_score:
            result.result = 'score'
            result.winner = 'player'
        elif d_score == p_score:
            result.result = 'tie'
        return result
