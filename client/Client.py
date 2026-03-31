from enum import Enum
import json
import socket
import UI
from Connection import Connection
from Game import Game
import paho.mqtt.client as mqtt
import uuid

class ClientState(Enum):
    OFFLINE = 0
    WAIT_CON = 1
    PLAYING = 2
    WAIT_QUEUE = 3


DECO = "disconnect"


def mqtt_on_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
    parsed_message = json.loads(message.payload)
    hostname = parsed_message.get("hostname")
    port = parsed_message.get("port")
    print(f"Connecting to the game server {hostname}:{port}")
    userdata.connect_server(f"{hostname}:{port}")
    client.disconnect()
    client.loop_stop()


def mqtt_on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed")

def mqtt_on_disconnect(client, userdata, reason_code):
    print("Disconnected from broker")

def mqtt_on_publish(client, userdata, mid):
    print("Published message", mid)

class QueueOperation(int, Enum):
    ADD = 0
    QUIT = 1


class ClientClass():
    def __init__(self) -> None:
        self.state = ClientState.OFFLINE
        self.ui = UI.UI(self)
        self.connection = Connection()
        self.game = Game("Map/Arenas", self)
        self.game.connection = self.connection
        self.num_connected_player = -1
        self.max_player = -1
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.user_data_set(self)
        self.mqtt_client.on_message = mqtt_on_message
        self.mqtt_client.on_subscribe = mqtt_on_subscribe
        self.mqtt_client.on_disconnect = mqtt_on_disconnect
        self.mqtt_client.on_publish = mqtt_on_publish
        self.unique_id = uuid.uuid4()
        self.server_host = ""

    def get_state(self):
        return self.state

    def get_max_player(self):
        return self.max_player

    def get_connected_player(self):
        return self.num_connected_player

    def is_connected(self):
        return self.connection.is_connected

    def run(self) -> None:
        running = True
        while running:

            packets = self.connection.receive_packets()

            # Update varié
            match self.state:
                case ClientState.OFFLINE:
                    pass
                case ClientState.WAIT_CON:
                    self.connection.has_connected(packets)
                    if not self.is_connected():
                        self.connect_server(self.server_host)
                    
                    for packet in packets:
                        if packet.decode("utf-8").find('{"n":') != -1:
                            obj = json.loads(packet.decode("utf-8"))
                            self.num_connected_player = obj.get("n")
                            self.max_player = obj.get("m")
                            print(self.num_connected_player, self.max_player)
                        if packet.decode("utf-8").find("map") != -1:
                            print(packet)
                            obj = json.loads(packet.decode("utf-8"))
                            for mapData in self.game.maps:
                                print(obj.get("map"))
                                if mapData.name == obj.get("map"):
                                    self.game.currentMap = mapData
                                    self.game.serverSize = obj.get("size")
                                    self.state = ClientState.PLAYING
                case ClientState.PLAYING:
                    self.ui.menu = UI.Menu.GAME
                    self.game.update_game(packets)

            running=self.ui.handle_event()
            self.ui.render()
    

    def game_over(self):
        self.ui.result.set_hide(False)
        self.ui.result_info.set_hide(False)

    def connect_queue(self, addr: str):
        host, port = (None, None) # initialization to help debugging
        try:
            host, port = addr.split(":")
        except:
            return
        self.mqtt_client.connect(host, int(port))
        self.mqtt_client.loop_start()
        self.mqtt_client.subscribe(f"clients/{str(self.unique_id)}", 2)

        payload = {"uuid": str(self.unique_id), "op": QueueOperation.ADD}
        print("payload to queue", json.dumps(payload))
        self.mqtt_client.publish("queue/add", json.dumps(payload), 2)

        self.state = ClientState.WAIT_QUEUE

    def quit_queue(self):
        payload = {"uuid": str(self.unique_id), "op": QueueOperation.QUIT}
        msg_info = self.mqtt_client.publish("queue/add", json.dumps(payload), 2)
        msg_info.wait_for_publish(3)
        self.state = ClientState.OFFLINE
        self.mqtt_client.disconnect()
        self.mqtt_client.loop_stop()

    def connect_server(self,addr : str) ->None: 
        self.server_host = addr
        print(f"Trying to connecto to {addr}")
        try:
            ip,port = addr.split(":")
            self.connection.send_connect((ip,int(port)))
            self.game.connection.server_address = (ip,int(port))
            self.state = ClientState.WAIT_CON
        except:
            pass

    def disconnect_server(self) ->None:
        self.connection.send_message(DECO)
        self.connection.is_connected=False
        print("disconnect")
        self.state = ClientState.OFFLINE

class loader:
    def loadCsv(csv):
        list= []
        with open(csv, "r") as file:
            for line in file:
                row = [cell for cell in line.strip().split(',')]
                list.append(row)
        return list
