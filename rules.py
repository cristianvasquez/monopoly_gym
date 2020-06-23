from typing import Any, Tuple
import numpy as np
from acme import specs

from gym.utils import seeding
from render import Winter_is_coming_renderer
from setup import DEFAULT_SETUP, MAX_APPLES_PER_SPOT, MAX_APPLES_PER_USER, Location_type, Action, MAX_TURNS
from variants import Winter, Summer
import dm_env

D_TYPE = np.float32


class Winter_is_coming(dm_env.Environment):
    '''
    ## Base rules

        * Thingies can move in the grid in four directions.
        * Thingies spend apples to move around.
        * From time to time, trees with apples appear in the grid
        * Thingies can collect apples from the trees
        * A thingy that doesn't have any apple left dies
        * Thingies can perform a fixed number of actions each turn.
        * The order in which thingies play is randomly chosen.
        * No more than one house or tree is allowed in the same spot.
    '''

    def __init__(self, setup=None, seed=None):
        if setup is None:
            setup = DEFAULT_SETUP
        self.np_random, seed = seeding.np_random(seed)
        self.setup = setup
        self._renderer = Winter_is_coming_renderer()

        # The player dies if go out of the screen
        if 'death_zone' in setup:
            self.death_zone = setup['death_zone']
        else:
            self.death_zone = False

        self._total_regret = 0.
        self.bsuite_num_episodes = 100

        self._actions_per_turn = setup['actions_per_turn']
        self._apple_gathering_capacity = setup['apple_gathering_capacity']
        turns_between_seasons = setup['turns_between_seasons']
        self._variants = []
        if 'summer' in setup:
            self._variants.append(Summer(turns_between_seasons, values=setup['summer'], seed=seed))
        if 'winter' in setup:
            self._variants.append(Winter(turns_between_seasons, values=setup['winter'], seed=seed))

        self.reset()

    def reset(self) -> dm_env.TimeStep:
        """Returns the first `TimeStep` of a new episode."""
        self.current_turn = 0
        self.players, self.grid = self._generate_objects()
        self.playing_queue = self._draw_new_playing_queue()
        return dm_env.restart(self._observation())

    def step(self, action: int) -> dm_env.TimeStep:
        """Updates the environment according to the action."""

        if self._terminal:
            raise RuntimeError("Terminal state reached")

        _grid_size_x, _grid_size_y, _ = self.grid.shape

        current_player_id = self.current_player
        (x, y), apples, actions_left, active = self.players[current_player_id]
        move_cost = self.setup['move_cost']

        if action == Action.MOVE_LEFT.value:
            if self.death_zone and x == 0:
                # falls off the cliff and dies
                active = False
                actions_left = 0
            else:
                x = x - 1 if x > 0 else x
                apples -= move_cost
        elif action == Action.MOVE_RIGHT.value:
            if self.death_zone and x == _grid_size_x - 1:
                # falls off the cliff and dies
                active = False
                actions_left = 0
            else:
                x = x + 1 if x < _grid_size_x - 1 else x
                apples -= move_cost
        elif action == Action.MOVE_UP.value:
            if self.death_zone and y == 0:
                # falls off the cliff and dies
                active = False
                actions_left = 0
            else:
                y = y - 1 if y > 0 else y
                apples -= move_cost
        elif action == Action.MOVE_DOWN.value:
            if self.death_zone and y == _grid_size_y - 1:
                # falls off the cliff and dies
                active = False
                actions_left = 0
            else:
                y = y + 1 if y < _grid_size_y - 1 else y
                apples -= move_cost
        elif action == Action.COLLECT_APPLES.value:
            _apples = self.grid[x, y, 1]
            if _apples > 0:
                # Player can only collect available apples
                gathered_apples = min(self._apple_gathering_capacity, _apples)
                apples += gathered_apples
                self.grid[x, y, 1] = _apples - gathered_apples

        elif action == Action.DO_NOTHING.value:
            pass

        actions_left = actions_left - 1

        # apply seasonal costs each time the turn ends
        if actions_left == 0:
            # Apply costs associated to variants
            for variant in self._variants:
                if variant.applies(self.current_turn):
                    apples -= variant.location_cost(self.grid, x, y)

        # Keep apples in bounds
        apples = max(apples, 0)
        apples = min(apples, MAX_APPLES_PER_USER)

        # if player has 0 apples, ... dies
        if apples == 0:
            active = False
            actions_left = 0

        # update the player
        updated_player = ((x, y), apples, actions_left, active)
        self.players[current_player_id] = updated_player

        reward = self.setup['reward_function'](updated_player,
                                               self.grid,
                                               self.get_variant_state_info(self.current_turn))

        self._next_turn()

        if self._terminal:
            return dm_env.termination(reward=reward, observation=self._observation())
        else:
            return dm_env.transition(reward=reward, observation=self._observation())
        # return self._observation(), reward, self._terminal, (active)

    def observation_spec(self) -> specs.BoundedArray:
        """Returns the observation spec."""
        return specs.BoundedArray(shape=self._observation().shape, dtype=self._observation().dtype,
                                  name="board", minimum=0, maximum=MAX_APPLES_PER_USER)

    def _observation(self) -> np.ndarray:

        bins = np.array([0.1, 5., 10., 15., 20., 25., 30., 35., 40., 45., 50.])

        players = []
        for _i, ((x, y), apples, actions_left, active) in enumerate(self.players):
            players.append(x)
            players.append(y)
            # players.append(apples)
            players.append(np.digitize(apples, bins))

            # players.append(actions_left)
            # players.append(1. if active else 0.)

        np_variant_info = []
        for variant, value in self.get_variant_state_info(self.current_turn):
            np_variant_info.append(variant)
            np_variant_info.append(value)

        result = np.concatenate(
            (np.array(players), np.digitize(self.grid[:, :, 1], bins).flatten(),
             np_variant_info
             ))

        # result = np.concatenate(
        #     (np.array(players), self.grid.flatten()))

        return np.array(result, copy=False, dtype=np.float32)

    def action_spec(self) -> specs.DiscreteArray:
        """Returns the action spec."""
        return specs.DiscreteArray(
            dtype=np.int, num_values=len(list(Action)), name="action")

    def random_state(self):
        '''
        A random state generator, used for testing purposes
        :return:
        '''
        current_player = self.np_random.randint(0, self.setup['number_of_players'])
        players, grid = self._generate_objects(
            tree_apples_bounds=(0, MAX_APPLES_PER_SPOT),
            player_apples_bound=(0, MAX_APPLES_PER_USER)
        )
        current_turn = self.np_random.randint(0, MAX_TURNS)
        return current_player, (grid, players, self.get_variant_state_info(current_turn))

    def _generate_objects(self, tree_apples_bounds=None, player_apples_bound=None):
        '''
        Generates a list of players and a grid with the objects of the game
        :param tree_apples_bounds:
        :param player_apples_bound:
        :return:
        '''
        _grid_size_x = self.setup['grid_size_x']
        _grid_size_y = self.setup['grid_size_y']
        _grid = np.zeros((_grid_size_x, _grid_size_y, 2), dtype=np.float32)

        all_spots = [(x, y) for x in list(range(_grid_size_x)) for y in list(range(_grid_size_y))]

        # Get random positions for players
        player_positions = self.np_random.choice(len(all_spots), self.setup['number_of_players'], replace=False)

        # The number of initial apples for each player can be random or not
        if player_apples_bound is None:
            player_apples_bound = (self.setup['initial_player_apples'], self.setup['initial_player_apples'] + 1)

        # coordinates, apples, actions_left, active
        players = [(all_spots[i],
                    self.np_random.randint(player_apples_bound[0], player_apples_bound[1]),
                    self._actions_per_turn, True)
                   for i in player_positions]

        number_of_houses_and_trees = self.setup['number_of_houses'] + self.setup['number_of_trees']
        assert number_of_houses_and_trees < _grid_size_x * _grid_size_y, "Not enough space for so many houses  and trees"

        # House allocation
        # Get random positions for houses and trees
        houses_and_trees_positions = self.np_random.choice(len(all_spots), number_of_houses_and_trees, replace=False)
        # Set houses in the grid
        for i in houses_and_trees_positions[:self.setup['number_of_houses']]:
            _x, _y = all_spots[i]
            _grid[_x, _y, :] = [Location_type.UNCLAIMED_HOUSE.value, 0]

        # Tree allocation
        # The number of initial apples in a tree can be random or not
        if tree_apples_bounds is None:
            tree_apples_bounds = (self.setup['initial_apples_per_tree'], self.setup['initial_apples_per_tree'] + 1)
        # Set trees in the grid
        for i in houses_and_trees_positions[self.setup['number_of_houses']:]:
            _x, _y = all_spots[i]
            _apples = self.np_random.randint(tree_apples_bounds[0], tree_apples_bounds[1])
            _grid[_x, _y, :] = [Location_type.TREE.value, _apples]

        return players, _grid

    def get_variant_state_info(self, current_turn):
        '''
        gets the state of all the variants applied to the game
        :param current_turn:
        :return:
        '''
        result = []
        for variant in self._variants:
            if variant.applies(current_turn):
                result.append(variant.state_info(current_turn))
        return result

    def render(self):
        return self._renderer.render(
            state=(self.grid, self.players, self.get_variant_state_info(self.current_turn)),
            current_turn=self.current_turn,
            current_player_id=self.current_player,
            playing_queue=self.playing_queue,
            is_terminal=self._terminal,
        )

    @property
    def current_player(self) -> id:
        '''
        Gets the id of the next player to perform actions
        :return:
        '''
        return self.playing_queue[0] if len(self.playing_queue) > 0 else None

    @property
    def player_ids(self) -> [int]:
        '''
        A list of all the players ids
        :return:
        '''
        return list(range(len(self.players)))

    def _active_with_actions(self, player_ids) -> [int]:
        '''
        A list of all the players that can perform actions in this turn
        :param players:
        :return:
        '''
        available = []
        for i in player_ids:
            (_, _, actions_left, active) = self.players[i]
            if active and actions_left > 0:
                available.append(i)
        return available

    def _draw_new_playing_queue(self) -> [int]:
        '''
        Generates a new random playing queue, with the player's ids
        :return:
        '''
        alive_players_ids = self._active_with_actions(self.player_ids)
        return self.np_random.choice(alive_players_ids, len(alive_players_ids), replace=False) if len(
            alive_players_ids) > 0 else []

    @property
    def _terminal(self) -> bool:
        '''
        If the game is in a terminal state or not
        :return:
        '''
        return self.current_player is None or self.current_turn > MAX_TURNS

    def _next_turn(self):

        # filter players that died, or don't have actions left
        self.playing_queue = self._active_with_actions(self.playing_queue)

        if len(self.playing_queue) == 0:
            # A new turn starts, update actions left
            for i, (coord, apples, _, active) in enumerate(self.players):
                if active:
                    self.players[i] = (coord, apples, self._actions_per_turn, active)  # Update actions

            # Draw another player queue
            self.playing_queue = self._draw_new_playing_queue()
            self.current_turn += 1

            # Apply all variants
            for variant in self._variants:
                if variant.applies(self.current_turn):
                    self.grid = variant.update_spots(self.grid)

    def bsuite_info(self):
        return dict(total_regret=self._total_regret)
