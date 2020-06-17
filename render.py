from gym.utils import colorize
from tabulate import tabulate

from lib.random_emoji import random_emoji


class Winter_is_coming_renderer:
    def __init__(self, number_of_players):
        # Select player emoticons and names
        self.token_emojis = [random_emoji() for i in range(number_of_players)]

    def render(self, grid_size_x, grid_size_y, current_turn=None, playing_queue=None, state=None, is_terminal=False, current_player_id=None):
        players, houses, trees, season, turns_until_season_change = state
        # build the grid and show it
        headers = [x for x in list(range(grid_size_x))]
        table = []

        def render_coord(x, y):

            # Render Players
            spot = ''
            for i, ((_x, _y), apples, actions_left, active) in enumerate(players):
                if x == _x and y == _y:
                    if not active:
                        spot += f'thingy_{i} RIP\n'
                    else:
                        spot += f'-->THINGY_{i}<-- ({apples})\n' if i == current_player_id else f'thingy_{i} ({apples})\n'

            # Render Houses
            for i, ((_x, _y), type) in enumerate(houses):
                if x == _x and y == _y:
                    spot += '{}_{}\n'.format('House', i)

            # Render Trees
            for i, ((_x, _y), apples_left) in enumerate(trees):
                if x == _x and y == _y:
                    spot += '{}_{} ({})\n'.format('Tree', i, apples_left)

            return spot

        for y in list(range(grid_size_y)):
            table.append([render_coord(x, y) for x in list(range(grid_size_x))])


        # coordinates, credits, actions_left, active_player = current_player
        status = f'current_turn:{current_turn}, season:{season}, turns_until_season_change:{turns_until_season_change}, playing_queue:{playing_queue}'

        if not is_terminal:
            ((_x, _y), apples, actions_left, active_player) = players[current_player_id]
            status += f'\ncurrent_player[{current_player_id}], coords: ({_x},{_y}), apples:({apples}), Actions left: {actions_left} '
        else:
            status += f'\nTerminal state'

        return '{}\n{}'.format(tabulate(table, headers, tablefmt="fancy_grid"), status)
