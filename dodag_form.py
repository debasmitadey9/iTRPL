import time
import gym
import argparse
import ns3gym
from ns3gym import ns3env
from functools import partial
from trickleTimer import trickleTimer
from gym import spaces
import numpy as np
import math
import random
from matplotlib import pyplot as plt

INFINITE_RANK = 0xffff
DEFAULT_MIN_HOP_RANK_INCREASE = 256
ROOT_RANK = DEFAULT_MIN_HOP_RANK_INCREASE
ALL_RPL_NODES = "ff02::1a"
DEFAULT_STEP_OF_RANK = 3
MINIMUM_STEP_OF_RANK = 1
MAXIMUM_STEP_OF_RANK = 9
DEFAULT_RANK_STRETCH = 0
MAXIMUM_RANK_STRETCH = 5
DEFAULT_RANK_FACTOR = 1
MINIMUM_RANK_FACTOR = 1
MAXIMUM_RANK_FACTOR = 4

# Load the module from the file path
#trickleTimer_module = imp.load_source('trickleTimer', '/content/trickleTimer.py')

# Import the class from the module
#trickleTimer = trickleTimer_module.trickleTimer


class RPLNode:

    def __init__(self, node_id, dodag_id, dodag_version, routing_table, failure_rate, is_root=False):
        self.node_id = node_id
        self.dodag_id = dodag_id
        self.dodag_version = dodag_version
        self.instanceID = 123
        self.DTSN = 0
        self.failure_rate = failure_rate
        self.parents = []
        self.rank = 0
        self.interfaces = {}


        self.DIOIntDoublings = 20
        self.DIOIntMin = 3
        self.DIORedundancyConst = 10


        if is_root:
            self.is_dodag_root = True
            self.rank = INFINITE_RANK

        self.compute_rank_increase = partial(compute_rank_increase, self)
        self.compare_parents = compare_parents

        self.last_dio = time.time()
        self.routing_table = {}

    def is_dodag_root(self):
        return self.rank == 0

    def add_parent(self, parent):
        self.parents.append(parent)

    def update_rank(self, new_rank):
        self.rank = new_rank

    def send_dis(self, destination, env, nodes,episode,num_episode, routing_table,s,iface=None, dodag_shutdown=False):
        if self.node_id in routing_table[1]:
            print("Sensing Sybil attack as node already present so aborting")
            return
        dis_message = self.create_dis_message()

        if iface and destination:
            self.interfaces[iface].send(destination,dis_message)

        if destination:
            destination.receive_dis(self,dis_message,env,nodes,episode,num_episode,routing_table,s)
        else:
            self.broadcast(dis_message)
        if not self.is_dodag_root and not dodag_shutdown:
            self.set_dis_timer()

        del dis_message

    def create_dis_message(self):
        parent_info = []

        for parent in self.parents:
          parent_info.append(f"ParentID={parent.node_id}, Rank={parent.rank}")

        dis_message = "instanceID={}, version={}, rank={}, G={}, DODAGID={}, Parents={}".format(
        self.instanceID, self.dodag_version, self.rank, self.is_dodag_root(), self.dodag_id, parent_info)

        return dis_message

    def receive_dis(self,node, dis_message,env,nodes,episode,num_episode,routing_table,s):
        print(f"Node {self.node_id} received DIS message: {dis_message}")
        state_old = env.get_state(nodes,episode,num_episode,routing_table,s)
        #check the routing table if the node exist in the routing table
        network_parameter = 1 - (node.failure_rate)
        trust = env.obtain_trust(self.node_id,routing_table,episode,network_parameter,s)
        print("Obtained trust of the node", trust)
        if trust<= 1 and trust >= 0.5:
            print("New node trying to join")
            self.send_dio(node,env,nodes,episode,num_episode,routing_table,s)
        if trust <0.5:
            print("Trust of node less than required value")
            return 0



    def send_dio(self, node,env, nodes, episode,num_episode,routing_table,s, iface=None, destination=None, dodag_shutdown=False ):
        dio_message = self.create_dio_message()

        if iface and destination:
            self.interfaces[iface].send(destination, dio_message)
        else:
            self.dio_broadcast(dio_message,node,env,nodes,episode,num_episode,routing_table,s)

        if not self.is_dodag_root and not dodag_shutdown:
            self.set_dao_timer()

        del dio_message

    def create_dio_message(self):
        dio_message = "instanceID={}, version={}, rank={}, G={}, DODAGID={}".format(
            self.instanceID , self.dodag_version, self.rank, self.is_dodag_root, self.dodag_id
        )
        return dio_message
        
    def leave(self,routing_table,nodes):
        # Remove the leaving node from the routing table
        print("Node to leave the DODAG",self.node_id)
        if self.node_id in routing_table:
            print("The routing table will be deleted")
            del routing_table[self.node_id]
               
    # Remove references to the leaving node from parents' routing entries
        for parent in self.parents:
            if parent.node_id in routing_table and self.node_id in routing_table[parent.node_id]:
                print("Routing Table of parent", routing_table[parent.node_id])
                del routing_table[parent.node_id][self.node_id]
        self.parents = []
        print("Node IDs before deleting:", [node.node_id for node in nodes])
        nodes_copy = nodes.copy()  # Create a copy of the list to avoid modifying it while iterating
        for node in nodes_copy:
            if node.node_id == self.node_id:
                nodes.remove(node)
        print("Node IDs after deleting:", [node.node_id for node in nodes])

#upon receiving dio , the next node in the node series sends dao
    def dio_broadcast(self,dio_message,node,env,nodes,episode, num_episode,routing_table,s):
        print(f"Node {self.node_id} broadcasting DIO message: {dio_message} by node",self.node_id, dio_message)
        node.send_dao(node,env,nodes,episode,num_episode,routing_table,s)


    def broadcast(self, message):
        print(f"Node {self.node_id} broadcasting message: {message}")

    def send_dao(self, destination, env, nodes, episode, num_episode,routing_table,s,source=None, iface=None):
        dao_message = self.create_dao_message()

        if iface and isinstance(destination, RPLNode):
            self.interfaces[iface].send(destination, dao_message)
        elif isinstance(destination, RPLNode):
            destination.receive_dao(env,nodes,episode,num_episode,routing_table,s)
            destination.send_dao_ack(source=source, destination=self, DAOsequence=123,env=env,episode=episode,num_episode=num_episode, routing_table = routing_table,s=s,nodes=nodes)
        else:
            self.broadcast(dao_message)
            destination.send_dao_ack(source=source, destination=destination, DAOsequence=123,env=env,episode=episode,num_episode=num_episode, routing_table = routing_table,s=s,nodes=nodes)

        del dao_message

    def receive_dao(self,env,nodes,episode,num_episode,routing_table,s):
        state = env.get_state(nodes,episode,num_episode,routing_table,s)

    def generate_dao_options(self):
        # Replace with the actual logic to generate DAO options
        options = {
            'option1': 'value1',
            'option2': 'value2',
            'option3': 'value3'
        }
        return options

    def create_dao_message(self):
        dao_message = dao_message = "instanceID={}, DODAGID={}, flags={}, DTSN={}, options={}".format(
            self.instanceID, self.dodag_id, 0, self.DTSN, self.generate_dao_options()
        )
        return dao_message

    def send_two_daos(self):
        if self.active:
            self.send_dao(destination=ALL_RPL_NODES, retransmit=True)
            self.send_dao()

    def send_dao_ack(self, source, destination, DAOsequence,env,episode,num_episode,routing_table,s,nodes):
        DAO_ACK_message = "instanceID={}, DODAGID={}, Daosequence={}, Status={}".format(
            self.instanceID, self.dodag_id, DAOsequence, 0
        )
        #print(f"Node {self.node_id} sending DAO_ACK message: {DAO_ACK_message} to Node {destination.node_id}")
        #After sending the dao_ack the reward will be calculated
        trust = env.compute_trust(self.node_id,episode,num_episode,routing_table,s,nodes)
        reward = env.compute_rewards(trust)
        
        return reward


    def set_dio_timer(self):
        try:
            self.dio_timer.cancel()
        except:
            pass

        self.dio_timer = trickleTimer(self.send_dio, {}, \
                                      Imin=0.001 * 2 ** self.DIOIntMin, \
                                      Imax=self.DIOIntDoublings, \
                                      k=self.DIORedundancyConst)
        self.dio_timer.start()

    def set_dao_timer(self):
        try:
            if not self.dao_timer.is_alive():
                self.dao_timer = Timer(DEFAULT_DAO_DELAY, self.send_two_daos)
            else:
                return
        except AttributeError:
            self.dao_timer = Timer(DEFAULT_DAO_DELAY, self.send_two_daos)

        self.dao_timer.start()
        #print(f"Node {self.node_id} setting DAO timer")

    def setDAO_ACKtimer(self):
        self.cancelDAO_ACKtimer()

        if self.DAO_trans_retry >= DEFAULT_DAO_MAX_TRANS_RETRY:
            self.DAO_trans_retry = 0
            self.DIOtimer.hear_inconsistent()

            return

        self.DAO_trans_retry += 1
        self.DAO_ACKtimer = threading.Timer(DEFAULT_DAO_ACK_DELAY, self.sendDAO, kwargs={
            'iface': self.DAO_ACK_source_iface, 'destination': self.DAO_ACK_source, 'retransmit': True})
        self.DAO_ACKtimer.start()

    def form_routing_table(self, node_id,routing_table,episode,nodes):
        
        if self.node_id not in routing_table:
                #print("adding node:",self.node_id," to routing table")
                routing_table.update({
                    self.node_id: {
                         self.node_id: (self.node_id, 1.0, 0, episode, 0)  # Replace the values as needed
                    }
                })
                #print("Routing table:",routing_table)
                #if the new node is not in parent routing table
        for parent in self.parents:
            #print("Parent:",parent.node_id)
            if self.node_id not in routing_table[parent.node_id]:
                #print("Self routing table", routing_table[self.node_id])
                existing_values = routing_table[self.node_id]
                updated_values = (
                self.node_id,
                existing_values[self.node_id][1],  # Existing trust value
                existing_values[self.node_id][2],  # Existing reward value
                existing_values[self.node_id][3] + 1,  # Increment the episode value
                existing_values[self.node_id][4] 
                )
                routing_table[parent.node_id][self.node_id] = updated_values
                #print("Parent Routing Table after adding node:",routing_table[parent.node_id])
                #add parent to self routing table
        for parent in self.parents:
            if parent.node_id in self.routing_table:
                existing_values = self.routing_table[parent.node_id]
                #print("Existing values:", existing_values[parent.node_id][2])
                updated_values = (
                parent.node_id,
                existing_values[parent.node_id][1],  # Existing trust value
                existing_values[parent.node_id][2],  # Existing reward value
                existing_values[parent.node_id][3] + 1,  # Increment the episode value
                existing_values[parent.node_id][4]  # Existing no_of_packets value
                )
                routing_table[self.node_id][parent.node_id] = updated_values
        #print("Routing table:",routing_table)



    def update_routing_table(self, routing_table, trust,reward,episode, no_of_packets):
        #print("The node ID which called the function:", str(self.node_id))
        for node_id, node_info in routing_table.items():
            updated_node_info = node_info.copy()
            updated_node_info[self.node_id] = (self.node_id, trust, reward, episode, no_of_packets)
            routing_table[node_id] = updated_node_info
            #print("Routing table for node:", node_id, "is:", routing_table[node_id])
        
    def join_dodag(self,node_id,routing_table,episode,nodes):
        self.form_routing_table(node_id,routing_table,episode,nodes)
        
       # print("Node ID that wants to join the dodag", self.node_id)
        #self.send_message("Hello", self.node_id)

    def drop_packet(self):
        print("Message is dropped")
        
    def send_message(self, message, node_id, destination, nodes,routing_table,episode,md):
        #print("The dodag node that wants to send message",node_id.node_id)
        #print("destination",destination.node_id)
        #print("self.routing_table", routing_table)
        if destination.node_id in routing_table[node_id.node_id]:
            #print("Destination routing table:",routing_table[destination.node_id])
            next_hop = routing_table[node_id.node_id][destination.node_id][0]
        #receive acknowledgement from next hop
            while next_hop:
                value = random.random()
                #print("Comparison value:",routing_table[node_id.node_id][destination.node_id][4])
                if value < routing_table[node_id.node_id][destination.node_id][4]:
                    #print("Failure rate might get changed")
                    trust = routing_table[node_id.node_id][destination.node_id][1]
                    reward = routing_table[node_id.node_id][destination.node_id][2]
                    episode = routing_table[node_id.node_id][destination.node_id][3]
                    no_of_packets = routing_table[node_id.node_id][destination.node_id][4] + 1
                    node_id.update_routing_table(routing_table,trust, reward, episode, no_of_packets)
                next_hop_routing_table = routing_table.get(next_hop, {})   
                if destination.node_id in next_hop_routing_table:
                    next_hop = next_hop_routing_table[destination.node_id][0]
                    if destination.node_id is next_hop:
                        #print("Message Delivered!")
                        md = md + 1
                        break
                else:
                    break
                                                                        
        #print("Node's failure rate before sending message:",node_id.failure_rate)
        if node_id in routing_table:
            node_id.failure_rate = routing_table[1][node_id.node_id][4] *0.1
        
        #print("Node's failure rate after sending message:",node_id.failure_rate)
        return md
        
    def create_new_nodes(self,nodeid):
        node_new = RPLNode(node_id=nodeid, dodag_id="dodag1", dodag_version=1, failure_rate= 0.1, routing_table=None)
        return node_new
        
    def create_malicious_node(self,nodeid):
        node_new = RPLNode(node_id=nodeid, dodag_id="dodag1", dodag_version=1, failure_rate= 0.8, routing_table=None)
        return node_new
        
    def dissolve(self, routing_table, nodes):
        routing_table.clear()
        nodes.clear()
        
    def change_parent(self, new_parent,routing_table,episode,network_parameter,s,env):
        # Replace a random parent node with a new parent node
        trust = env.obtain_trust(self.node_id,routing_table,episode,network_parameter,s)
        if trust > 0.5:
            if self.parents:
                index_to_replace = random.randint(0, len(self.parents) - 1)
                self.parents[index_to_replace] = new_parent
                
        else:
            print("Malicious node trying to change parents")
        
class MultiAgentEnv:
    def __init__(self, dodag, node, current_node, routing_table):
        self.dodag = dodag
        self.node = node
        self.current_node = current_node
        self.routing_table = routing_table
        self.num_agents = len(node)
        self.states = [0] * self.num_agents
        self.rewards = [0] * self.num_agents



#the state returns the trust value of the whole DODAG
    def get_state(self, nodes, episode, num_episode,routing_table,s):
      state = 0
      for node in nodes:
          # Calculate the trust score for the node based on its ID or other relevant information
          if node.node_id in routing_table:
              trust_score = routing_table[node.node_id][node.node_id][1]
              #print("Trust score of node_id:", node.node_id, " is:", trust_score)
          state += trust_score
      #print("State before generalization:", state)
      state /= len(nodes)
      #print("State after generalization:", state)
      #print("Length of nodes",len(nodes))
      return state




      #obtain trust from routing table
    def obtain_trust(self, node_id,routing_table,episode,network_parameter,s):
        t = 0 #weighted trust
        for neighbors in self.routing_table.values():
            #print("Neighbour for obtaining trust:", neighbors)
            #print("Node_id: ", node_id)
            if node_id in neighbors:
                trust = neighbors[node_id][1]
                episode = neighbors[node_id][3]
                #print("Trust:",trust,"Episode:",episode)
                weight =  (math.e)**(-network_parameter * (680-episode))  
                #print("Weight:",weight)
                t = t + (weight*trust)
                #print("Weighted Trust for node:",node_id, "is:",t)
                
            else:
                t = 1
        
        return t

    def calculate_t(self):
        t = random.random()
        return t

    def compute_trust(self, node_id,episode,num_episode,routing_table,s,nodes):
    # Compute and return the rewards for the current state
        b = 90
        c = 0.1
        #t = self.calculate_t() #here t is the number of misbehaviour instances reported need to be calculated
        #print("node_id:",node_id)
        network_parameter = nodes[node_id-1].failure_rate
        #network_parameter = 1 - network_parameter
        t = 1-network_parameter
        #print("Network parameter", network_parameter)
        initial_trust=self.obtain_trust(node_id,routing_table,episode,network_parameter,s)
        #print("Initial trust obtained:",initial_trust)
        trust = self.inv_gompertz(initial_trust, b, c, t)
        if trust>1:
            trust = 1
        return trust

    def compute_rewards(self, trust):
    	if trust < 0.5:
        	return -1
    	else:
        	return 1


    def inv_gompertz(self, initial_trust, b, c, t):
        trust = 1 - initial_trust*math.exp(-b * math.exp(-c * t))
        return trust

    def policy(self, state):

        # Return the selected action
        #print("The state of the DODAG:",state)
        if state>0.7:
          selected_action = "Join"

        else:
          selected_action = "Leave"
        return selected_action


    def calculate_value_function(self, routing_table,episode,network_parameter,s):
        # Initialize Q-values
        states = ['H', 'L']
        actions = ['R', 'D']
        Q = np.zeros((len(states), len(actions)))

     # Q-learning parameters
        alpha = 0.1  # Learning rate
        gamma = 0.7  # Discount factor
        epsilon = 0.1  # Exploration rate

      # Number of episodes
        num_episodes = 10

      # Q-learning algorithm
        for episode in range(num_episodes):
            state = random.choice(states)
    
        for _ in range(10000):  # Limited steps per episode to prevent infinite loops
            if random.uniform(0, 1) < epsilon:
                action = random.choice(actions)  # Explore
            else:
            # Exploit using the Q-values
                max_q_value = np.max(Q[states.index(state)])
                best_actions = [actions[i] for i in range(len(actions)) if Q[states.index(state)][i] == max_q_value]
                action = random.choice(best_actions)
        
            # Simulate a transition to the next state (randomly chosen)
            next_state = random.choice(states)
        
        # Calculate the reward based on the transition
            if (state, action, next_state) == ('H', 'R', 'L'):
                reward = -1
            elif (state, action, next_state) == ('H', 'D', 'L'):
                reward = 1
            elif (state, action, next_state) == ('L', 'R', 'H'):
                reward = 1
            elif (state, action, next_state) == ('L', 'D', 'H'):
                reward = -1
            else:
                reward = 0
        
        # Update Q-value
            Q[states.index(state)][actions.index(action)] += alpha * (
                reward + gamma * np.max(Q[states.index(next_state)]) - Q[states.index(state)][actions.index(action)]
            )
        
            state = next_state  # Move to the next state
        return Q
        # The Q array now contains the learned Q-values



        
def compute_rank_increase(dodag, parent_rank):
    rank_increase = (DEFAULT_STEP_OF_RANK * DEFAULT_RANK_FACTOR + DEFAULT_RANK_STRETCH) * dodag.MinHopRankIncrease
    if parent_rank + rank_increase > INFINITE_RANK:
        return INFINITE_RANK
    else:
        return parent_rank + rank_increase


def compare_parents(parent1, parent2):
    """Compare two parents"""
    if parent1.rank != parent2.rank:
        return parent1.rank - parent2.rank



    return 0




def main():
    routing_table = {}
#initial RPL function for forming the initial DODAG
    # Create RPL nodes
    node1 = RPLNode(node_id=1, dodag_id="dodag1", dodag_version=1, failure_rate = 0, routing_table=None,is_root=True)
    node2 = RPLNode(node_id=2, dodag_id="dodag1", dodag_version=1, failure_rate= 0.1, routing_table=None)
    node3 = RPLNode(node_id=3, dodag_id="dodag1", dodag_version=1, failure_rate= 0.1, routing_table=None)
    node4 = RPLNode(node_id=4, dodag_id="dodag1", dodag_version=1, failure_rate= 0.1, routing_table=None)
    
    #adding the nodes in a list
    nodes = [node1,node2,node3,node4]
    # Add parents to nodes
    #there will be an exixting DODAG, then on that, nodes will be added and tested with RL
    node2.add_parent(node1)
    node3.add_parent(node1)
    node4.add_parent(node1)
    # Update ranks
    node2.update_rank(1)
    node3.update_rank(2)
    node4.update_rank(3)
    #comparing parent
    result = compare_parents(node2.parents[0], node3.parents[0])
    #print(f"Comparison result: {result}")
    flag = 3
    node = nodes[flag]

   # Call send_dio method on node1
   # node1.send_dio(node,env)

    # Call send_dao method on node2
   # node2.send_dao(node2,node3)

    num_episode = 1596
    routing_table = {
        node1.node_id: {
            node1.node_id: ('1',0.93,0,1,0),
            node2.node_id: ('2', 0.9,0,1,0),
            node3.node_id: ('3', 0.6,0,1,0),
            node4.node_id: ('4', 0.76,0,1,0),
        },
        node2.node_id: {
            node2.node_id: ('2', 0.9,0,1,0),
            node1.node_id: ('1', 0.93,0,1,0),
            node3.node_id: ('3', 0.6,0,1,0),
            node4.node_id: ('4', 0.76,0,1,0),
        },
        node3.node_id: {
            node3.node_id: ('3', 0.6,0,1,0),
            node1.node_id: ('1', 0.93,0,1,0),
            node2.node_id: ('2', 0.9,0,1,0),
            node4.node_id: ('4', 0.76,0,1,0),
        },
        node4.node_id: {
            node4.node_id: ('4', 0.76,0,1,0),
            node1.node_id: ('1', 0.93,0,1,0),
            node2.node_id: ('3', 0.9,0,1,0),
            node3.node_id: ('5', 0.6,0,1,0),
        },
        # Add other nodes and their corresponding neighboring nodes, trust values, reward, episode, no. of packets dropped
    }
    node1.join_dodag(node_id=1,routing_table=routing_table,episode=0, nodes = nodes)
    node2.join_dodag(node_id=2,routing_table=routing_table,episode=0, nodes = nodes)
    node3.join_dodag(node_id=3,routing_table=routing_table,episode=0, nodes = nodes)
    node4.join_dodag(node_id=4,routing_table=routing_table,episode=0, nodes = nodes)

    #for node_id, neighbors in routing_table.items():
        #print("Routing Table for Node", node_id)
        #for neighbor, (next_hop, trust, reward, episode, no_of_packets) in neighbors.items():
            #print(f"Destination: {neighbor}, Next Hop: {next_hop}, Trust: {trust}, Reward: {reward}, Episode:{episode}, No of packets dropped:{no_of_packets}")


    flag = 3
    v_flag = 1
    network_parameter = 0.5
    ep = 1
    s = {}
    state = {}
    value_function = {}
    env = MultiAgentEnv(dodag="dodag_1",node="nodes",current_node="node1",routing_table=routing_table)
    node = nodes[3]
    ms = 0
    md = 0
    for episode in range(1,num_episode+1):
#parent node calculates trust
#creating object of MultiAgentEnv class
        if flag > len(nodes):
            flag = 3
        md = nodes[2].send_message("Hello", nodes[2], nodes[3], nodes[2],routing_table,episode,md)
        ms = ms +1
        #node_info_generator = ("Nodes: " + str(node.node_id) for node in nodes)
        # Iterate through the generator and print each string
        #for node_info in node_info_generator:
            #print(node_info)
        state = env.get_state(nodes, episode, num_episode,routing_table,s)
        s[ep] = state
        ep=ep+1
        #print("This is for episode:",episode,"and flag:",flag)
        index1 = nodes.index(node)
        if index1 < len(nodes) - 1:
            node = nodes[index1+1]
        else:
            #create new nodes
            if episode%2 == 0:
                node_new = node.create_malicious_node(index1+2)
                print("Node Id that is malicious:", node_new.node_id)
            else:
                node_new = node.create_new_nodes(index1+2) #as index is always 1 less than id, and we will be creating next node so it is 2 less
            #print("New node is created")
            #append the new node to list
            nodes.append(node_new)
            #print("New length of node after creation", len(nodes))
            node = node_new
        #print("Enter the choice as root node, 1. To add nodes by the root, 2. The foreign node wants to join the DODAG")
        choic = random.choice([1,2])
        c = random.choice([0,1,2,3])
        if choic == "1":            
            nodes[c].send_dio(node,env,nodes,episode,num_episode,routing_table,s)
            node.add_parent(nodes[c])
            node.join_dodag(node_id=node,routing_table=routing_table,episode=episode,nodes=nodes)
            
        else:
            node.send_dis(nodes[c],env,nodes,episode,num_episode,routing_table,s)
            node.add_parent(nodes[c])
            node.join_dodag(node_id=node,routing_table=routing_table,episode=episode,nodes=nodes)
            
       
#this part will estimate the action for the immediate state
        action = env.policy(state)
        if action == "Join":

            #print("JOIN")
            trust = env.compute_trust(node.node_id,episode,num_episode,routing_table,s,nodes)
            #print("Computed trust of the node:",trust)
            if trust <0.5:
                reward = -1
            else:
                reward = 1
            #print("Value of node calling the update_routing_table function is:",str(node.node_id))
            no_of_packets = node.failure_rate *10
            node.update_routing_table(routing_table,trust,reward,episode,no_of_packets)
            flag = flag + 1
            
        else:
            #print("Action chosen is Leave so the node will not be added")
            if node.node_id in [1,2,3,4]:
                node.dissolve(nodes,routing_table)                  
                
                #create node 1 to 4
                for node_id in range(1, 5):
                    node_new = node.create_new_nodes(node_id)
                    nodes.append(node_new)

                                        
                routing_table = {
                    node1.node_id: {
                        node1.node_id: ('1',0.93,0,1,0),
                        node2.node_id: ('2', 0.9,0,1,0),
                        node3.node_id: ('3', 0.6,0,1,0),
                        node4.node_id: ('4', 0.76,0,1,0),
                    },
                    node2.node_id: {
                        node2.node_id: ('2', 0.9,0,1,0),
                        node1.node_id: ('1', 0.93,0,1,0),
                        node3.node_id: ('3', 0.6,0,1,0),
                        node4.node_id: ('4', 0.76,0,1,0),
                    },
                    node3.node_id: {
                        node3.node_id: ('3', 0.6,0,1,0),
                        node1.node_id: ('1', 0.93,0,1,0),
                        node2.node_id: ('2', 0.9,0,1,0),
                        node4.node_id: ('4', 0.76,0,1,0),
                    },
                    node4.node_id: {
                        node4.node_id: ('4', 0.76,0,1,0),
                        node1.node_id: ('1', 0.93,0,1,0),
                        node2.node_id: ('3', 0.9,0,1,0),
                        node3.node_id: ('5', 0.6,0,1,0),
                    },
        # Add other nodes and their corresponding neighboring nodes, trust values, reward, episode, no. of packets dropped
               }
                node = nodes[3]
            else:   
                node.leave(routing_table,nodes)
                node = nodes[index1-1]
                
        for i in range(1,21):
            node_id = random.choice(nodes)
            destination = random.choice(nodes)
            #print("Sending message by node:",node_id.node_id)
            #print("Receiving message by node:",destination.node_id)
            message = "hi"
            ms = ms+1
            md = node_id.send_message(message, node_id, destination, nodes,routing_table,i,md)
                
        print("Packet Delivery rate:",md/ms)
        ms = 1
        md = 1
        #change parents
        new_parent_id = 4  # ID of the new parent node
        node_to_change = random.choice(nodes)  # Select a random node
        network_parameter = node_to_change.failure_rate
        node_to_change.change_parent(new_parent_id,routing_table,episode,network_parameter,s,env)
            
        if episode%10 == 0:
	        #calculate value function after 10 episodes and check the graph, we are using epsilon-greedy method
	    #sending messages by dodag nodes
            for i in range(1,11):
                node_id = random.choice(nodes)
                destination = random.choice(nodes)
                #print("Sending message by node:",node_id.node_id)
                #print("Receiving message by node:",destination.node_id)
                message = "hi"
                ms = ms+1
                md = node_id.send_message(message, node_id, destination, nodes,routing_table,i,md)
            Q = env.calculate_value_function(routing_table,episode,network_parameter,s)
            print("Packet Delivery rate:",md/ms)
            ms = 1
            md = 1
            print(Q)
            aggregate_trust = sum(s[i] for i in range(1,11))
            print("Aggregated trust:",aggregate_trust)
            maxim = 0
            print("Q[low_trust][retain]", Q[0][0])
            print("Q[low_trust][dissolve]", Q[0][1])
            print("Q[high_trust][retain]", Q[1][0])
            print("Q[high_trust][dissolve]", Q[1][1])             
            for i in range(2):
                for j in range(2):
                    if Q[i][j] > maxim:
                        action = j
                        maxim = Q[i][j]
                        
            if action is 0:
                node_id = nodes.index(node)
                node_id = node_id + 2
                print("The maximum value:", maxim, "Action chosen is retain")
                #create new nodes
                node_new = node.create_new_nodes(node_id)
                #append the new node to list
                nodes.append(node_new)
                #change the flag value to nodeid
                flag = node_id
            else:
                print("The chosen action is dissolve")
                node_id.dissolve(nodes,routing_table)                  
                
                #create node 1 to 4
                for node_id in range(1, 5):
                    node_new = node.create_new_nodes(node_id)
                    nodes.append(node_new)
                                        
                routing_table = {
                    node1.node_id: {
                        node1.node_id: ('1',0.93,0,1,0),
                        node2.node_id: ('2', 0.9,0,1,0),
                        node3.node_id: ('3', 0.6,0,1,0),
                        node4.node_id: ('4', 0.76,0,1,0),
                    },
                    node2.node_id: {
                        node2.node_id: ('2', 0.9,0,1,0),
                        node1.node_id: ('1', 0.93,0,1,0),
                        node3.node_id: ('3', 0.6,0,1,0),
                        node4.node_id: ('4', 0.76,0,1,0),
                    },
                    node3.node_id: {
                        node3.node_id: ('3', 0.6,0,1,0),
                        node1.node_id: ('1', 0.93,0,1,0),
                        node2.node_id: ('2', 0.9,0,1,0),
                        node4.node_id: ('4', 0.76,0,1,0),
                    },
                    node4.node_id: {
                        node4.node_id: ('4', 0.76,0,1,0),
                        node1.node_id: ('1', 0.93,0,1,0),
                        node2.node_id: ('3', 0.9,0,1,0),
                        node3.node_id: ('5', 0.6,0,1,0),
                    },
        # Add other nodes and their corresponding neighboring nodes, trust values, reward, episode, no. of packets dropped
               }
                flag = node_id 
                env = MultiAgentEnv(dodag="dodag_1",node="nodes",current_node="node1",routing_table=routing_table)
                node = nodes[3]       
                v_flag = v_flag+1
                ep = 1
                
            
    #print("Reward:",reward)

    #send dis from node5 to node1
    #node5.send_dis(node1,env,nodes,episode,num_episode)

    #plt.plot(v_flag,value_function)
    for node_id, neighbors in routing_table.items():
        print("Routing Table for Node", node_id)
        for neighbor, (next_hop, trust,reward,episode,no_of_packets) in neighbors.items():
            print(f"Destination: {neighbor}, Next Hop: {next_hop}, Trust: {trust}, Reward: {reward}, Episode: {episode}, No_of packets_dropped: {no_of_packets}")
            
    

if __name__ == "__main__":
	main()
