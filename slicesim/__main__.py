import math
import os
import random
import sys
import logging
from typing import Any

import simpy
import yaml

from .BaseStation import BaseStation
from .Client import Client
from .Coverage import Coverage
from .Distributor import Distributor
from .Graph import Graph
from .Slice import Slice
from .Stats import Stats

from .utils import KDTree

def validate_config(data: dict) -> None:
    """
    Validate the required fields in the YAML configuration.
    """
    required_settings = ['simulation_time', 'num_clients', 'limit_closest_base_stations', 'statistics_params', 'plotting_params']
    for key in required_settings:
        if key not in data.get('settings', {}):
            raise ValueError(f"Missing required setting: {key}")
    if 'slices' not in data:
        raise ValueError("Missing 'slices' section in config.")
    if 'clients' not in data:
        raise ValueError("Missing 'clients' section in config.")
    if 'base_stations' not in data:
        raise ValueError("Missing 'base_stations' section in config.")
    if 'mobility_patterns' not in data:
        raise ValueError("Missing 'mobility_patterns' section in config.")

def get_dist(d: str) -> Any:
    return {
        'randrange': random.randrange, # start, stop, step
        'randint': random.randint, # a, b
        'random': random.random,
        'uniform': random.uniform, # a, b
        'triangular': random.triangular, # low, high, mode
        'beta': random.betavariate, # alpha, beta
        'expo': random.expovariate, # lambda
        'gamma': random.gammavariate, # alpha, beta
        'gauss': random.gauss, # mu, sigma
        'lognorm': random.lognormvariate, # mu, sigma
        'normal': random.normalvariate, # mu, sigma
        'vonmises': random.vonmisesvariate, # mu, kappa
        'pareto': random.paretovariate, # alpha
        'weibull': random.weibullvariate # alpha, beta
    }.get(d)

def get_random_mobility_pattern(vals, mobility_patterns):
    i = 0
    r = random.random()
    while vals[i] < r:
        i += 1
    return mobility_patterns[i]

def get_random_slice_index(vals):
    i = 0
    r = random.random()
    while vals[i] < r:
        i += 1
    return i

def main():
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 2:
        logging.error('Please type an input file.')
        logging.error('python -m slicesim <input-file>')
        exit(1)

    # Read YAML file
    CONF_FILENAME = os.path.join(os.path.dirname(__file__), sys.argv[1])
    try:
        with open(CONF_FILENAME, 'r') as stream:
            data = yaml.load(stream, Loader=yaml.FullLoader)
    except FileNotFoundError:
        logging.error(f'File Not Found: {CONF_FILENAME}')
        exit(0)
    except Exception as e:
        logging.error(f'Error reading config: {e}')
        exit(1)

    try:
        validate_config(data)
    except Exception as e:
        logging.error(f'Config validation error: {e}')
        exit(1)

    random.seed()
    env = simpy.Environment()

    SETTINGS = data['settings']
    SLICES_INFO = data['slices']
    NUM_CLIENTS = SETTINGS['num_clients']
    MOBILITY_PATTERNS = data['mobility_patterns']
    BASE_STATIONS = data['base_stations']
    CLIENTS = data['clients']

    if SETTINGS['logging']:
        sys.stdout = open(SETTINGS['log_file'],'wt')
    else:
        sys.stdout = open(os.devnull, 'w')

    collected, slice_weights = 0, []
    for __, s in SLICES_INFO.items():
        collected += s['client_weight']
        slice_weights.append(collected)

    collected, mb_weights = 0, []
    for __, mb in MOBILITY_PATTERNS.items():
        collected += mb['client_weight']
        mb_weights.append(collected)

    mobility_patterns = []
    for name, mb in MOBILITY_PATTERNS.items():
        mobility_pattern = Distributor(name, get_dist(mb['distribution']), *mb['params'])
        mobility_patterns.append(mobility_pattern)

    usage_patterns = {}
    for name, s in SLICES_INFO.items():
        usage_patterns[name] = Distributor(name, get_dist(s['usage_pattern']['distribution']), *s['usage_pattern']['params'])

    base_stations = []
    i = 0
    for b in BASE_STATIONS:
        slices = []
        ratios = b['ratios']
        capacity = b['capacity_bandwidth']
        for name, s in SLICES_INFO.items():
            s_cap = capacity * ratios[name]
            s = Slice(name, ratios[name], 0, s['client_weight'],
                      s['delay_tolerance'],
                      s['qos_class'], s['bandwidth_guaranteed'],
                      s['bandwidth_max'], s_cap, usage_patterns[name])
            s.capacity = simpy.Container(env, init=s_cap, capacity=s_cap)
            slices.append(s)
        base_station = BaseStation(i, Coverage((b['x'], b['y']), b['coverage']), capacity, slices)
        base_stations.append(base_station)
        i += 1

    ufp = CLIENTS['usage_frequency']
    usage_freq_pattern = Distributor(f'ufp', get_dist(ufp['distribution']), *ufp['params'], divide_scale=ufp['divide_scale'])

    x_vals = SETTINGS['statistics_params']['x']
    y_vals = SETTINGS['statistics_params']['y']
    stats = Stats(env, base_stations, None, ((x_vals['min'], x_vals['max']), (y_vals['min'], y_vals['max'])))

    clients = []
    for i in range(NUM_CLIENTS):
        loc_x = CLIENTS['location']['x']
        loc_y = CLIENTS['location']['y']
        location_x = get_dist(loc_x['distribution'])(*loc_x['params'])
        location_y = get_dist(loc_y['distribution'])(*loc_y['params'])

        mobility_pattern = get_random_mobility_pattern(mb_weights, mobility_patterns)

        connected_slice_index = get_random_slice_index(slice_weights)
        c = Client(i, env, location_x, location_y,
                   mobility_pattern, usage_freq_pattern.generate_scaled(), connected_slice_index, stats)
        clients.append(c)

    KDTree.limit = SETTINGS['limit_closest_base_stations']
    KDTree.run(clients, base_stations, 0)

    stats.clients = clients
    env.process(stats.collect())

    env.run(until=int(SETTINGS['simulation_time']))

    for client in clients:
        logging.info(client)
        logging.info(f'\tTotal connected time: {client.total_connected_time:>5}')
        logging.info(f'\tTotal unconnected time: {client.total_unconnected_time:>5}')
        logging.info(f'\tTotal request count: {client.total_request_count:>5}')
        logging.info(f'\tTotal consume time: {client.total_consume_time:>5}')
        logging.info(f'\tTotal usage: {client.total_usage:>5}')
        logging.info('')

    logging.info(stats.get_stats())

    if SETTINGS['plotting_params']['plotting']:
        xlim_left = int(SETTINGS['simulation_time'] * SETTINGS['statistics_params']['warmup_ratio'])
        xlim_right = int(SETTINGS['simulation_time'] * (1 - SETTINGS['statistics_params']['cooldown_ratio'])) + 1
        
        graph = Graph(base_stations, clients, (xlim_left, xlim_right),
                      ((x_vals['min'], x_vals['max']), (y_vals['min'], y_vals['max'])),
                      output_dpi=SETTINGS['plotting_params']['plot_file_dpi'],
                      scatter_size=SETTINGS['plotting_params']['scatter_size'],
                      output_filename=SETTINGS['plotting_params']['plot_file'])
        graph.draw_all(*stats.get_stats())
        if SETTINGS['plotting_params']['plot_save']:
            graph.save_fig()
        if SETTINGS['plotting_params']['plot_show']:
            graph.show_plot()

    sys.stdout = sys.__stdout__

if __name__ == "__main__":
    main()
