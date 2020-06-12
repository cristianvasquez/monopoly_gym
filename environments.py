import random

import gym
from gym import spaces
from gym.utils import seeding

from board import Board
from monopoly_rules import MonopolicRules

class Monopoly(gym.Env):
    """Custom Environment that follows gym interface"""
    metadata = {'render.modes': ['human']}

    def __init__(self, number_of_players=2, max_turns=10000, board_file='board.csv'):
        super(Monopoly, self).__init__()  # Define action and observation space

        self.max_turns = max_turns
        self.board = Board(number_of_players=number_of_players, board_file=board_file)
        self.game = MonopolicRules(board=self.board, max_turns=self.max_turns)
        self.action_space = spaces.Discrete(len(self.game.actions))
        """
        A tuple (i.e., product) of simpler spaces

        Example usage:
        self.observation_space = spaces.Tuple((spaces.Discrete(2), spaces.Discrete(3)))
        """
        # TODO
        self.observation_space = spaces.Tuple((spaces.Discrete(2), spaces.Discrete(3)))

    def step(self, action):
        # Execute one time step within the environment
        return self.game.step(action)

    def state(self):
        return self.game.state()

    def possible_actions(self):
        return self.game.possible_actions()

    def reset(self):
        self.game = MonopolicRules(board=self.board, max_turns=self.max_turns)
        return self.game.state()

    def render(self, mode='human', close=False):
        # Render the environment to the screen
        print(self.board.render(self.game))

    def seed(self, seed=None):
        self.np_random, seed = seeding.np_random(seed)
        self.game.np_random = self.np_random
        return [seed]

