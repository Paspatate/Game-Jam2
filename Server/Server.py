"""
# Documentation du protocole de communication implémenté
## Format
Le server utilise des strings utf-8 encodé (bytes python comme b"")

## Connection
- Le client doit envoyer un string b"ping".
- Si le server a ajouter le client au server alors il renverra b"pong" pour accépté la connection

## Début du jeu
- Le server envoie un packet indiquant le début du jeu par un objet JSON contenant le nom de la map jouer
## Transmition en jeu
- Le Client doit envoyer les keycodes pygame pour les touches dans un array JSON. Exemple: touche 'd' appuyer -> message envoyer: b"[100]"
- Le server envoye les informations du monde dans un objet JSON.
Exemple: 
{
    1: {"pos": [45, 387]},
    2: {"pos": [847, 29]}
}
"""
import os,sys

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'client'))

import json
import pygame, pytmx
from enum import Enum
from time import sleep, time
from Player import Player
from ServerConnection import ServerConnection
from TmxMap import Map

TARGET_TPS = 60
BUFFER_SIZE = 1024

PING = b"ping"
PONG = b"pong"
DECO = b"disconnect"


class ServerState(Enum):
    WAIT_CON = 0
    GAME_SETUP = 1
    PLAYING = 2
    END_GAME = 3
    DIED = 4

class Server:
    def __init__(self, config: dict) -> None:
        print(f"{config=}") 

        self.server_connection = ServerConnection(self, (config.get("server_ip"), config.get("server_port")))

        self.state = ServerState.WAIT_CON
        
        self.maps = {1: "map1"}
        self.entities: dict[int, Player] = dict()
        self.client_addr = dict()
        self.NUM_PLAYER = config.get("num_player")
        self.next_net_id = 0

        self.delta_time = 0

        self.colliders = []

        self.game_start = 0
        self.running = False
    
    def new_net_id(self) -> int:
        self.next_net_id += 1
        return self.next_net_id

    def create_player(self, net_id:int) -> None:
        self.entities[net_id] = Player(self)
    
    def run(self) -> None:
        """Boucle principale du server"""
        self.running = True
        compute_time = 0
        print("Start server")
        while self.running:
            start_delta_time = time()
            start_compute_time = time()
            match self.state:
                case ServerState.WAIT_CON:
                    self.connect_player()
                case ServerState.GAME_SETUP:
                    self.setup_game()
                case ServerState.PLAYING:
                    self.update_game()
                case ServerState.END_GAME:
                    self.end_game()
            
            compute_time = start_compute_time - time()
            sleep(max((1/TARGET_TPS) - compute_time, 0))
            self.delta_time = start_delta_time - time()
    
    def connect_player(self) -> None:
        """Tente la connection de nouveau joueur"""
        incoming_packets = self.server_connection.receive_all_packet()

        for p, addr in incoming_packets:
            if p == PING:
                self.add_client(addr)
                player_info = {}
                player_info["n"] = len(self.client_addr)
                player_info["m"] = self.NUM_PLAYER
                self.server_connection.sendto_all_client((json.dumps(player_info)).encode('utf-8'))
            elif p == DECO:
                self.remove_client(addr)
        
        if len(self.client_addr) == self.NUM_PLAYER:
            self.state = ServerState.GAME_SETUP
            print("INFO: Starting game !")
     
    def add_client(self, new_addr: tuple[str, int]) -> None:
        if self.client_addr.get(new_addr) == None: # verification si déja connecter

            player_net_id = self.new_net_id()
            self.client_addr[new_addr] = player_net_id
            self.create_player(player_net_id)

            print(f"INFO: New connection from {new_addr} with network id {self.next_net_id}")
            client_info = dict()
            client_info[PONG.decode("utf-8")] = ""
            client_info["nid"] = player_net_id
            self.server_connection.sendto(json.dumps(client_info).encode("utf-8"), new_addr)

    def remove_client(self, addr):
        if self.client_addr.get(addr) != None:
            del self.entities[self.client_addr.get(addr)]
            del self.client_addr[addr]
            print("removed client ", addr)

    def setup_game(self) -> None:
        """Envoie le paquet pour le début de jeu"""
        packet = dict()
        packet["map"] = "Default"
        packet["size"] = (800,600)

        pygame.display.init()
        pygame.display.set_mode((800,600))

        self.load_maps()
        
        self.colliders = self.load_map_rects(self.maps[0].data)

        for e in self.entities.keys():
            self.entities[e].position.x = self.maps[0].spawn_position[e % len(self.maps[0].spawn_position)][0]
            self.entities[e].position.y = self.maps[0].spawn_position[e % len(self.maps[0].spawn_position)][1]

        self.server_connection.sendto_all_client(json.dumps(packet).encode("utf-8"))
        pygame.display.quit()
        self.game_start = time()
        self.state = ServerState.PLAYING

    def update_game(self) -> None:
        """Mise à jours de l'état du jeu"""

        inc_packet = self.server_connection.receive_all_packet()

        # Change les actions reçu 
        for data, addr in inc_packet:
            if data == DECO:
                self.remove_client(addr)
            else:
                content = data.decode("utf-8")
                try:
                    action_dict = json.loads(content)
                except:
                    continue
                net_id = self.client_addr.get(addr)
                if net_id is not None:
                    self.entities[net_id].set_action(action_dict)

        for e_id in self.entities.keys():
            self.entities[e_id].update(self.delta_time)
        
        if self.count_alive_player() == 1:
            self.state = ServerState.END_GAME
        
        serialized_entities = self.serialize_entities()
        
        self.server_connection.sendto_all_client(serialized_entities.encode("utf-8"))
    
    def serialize_entities(self) -> str:
        entities_dict = dict()
        
        for e in self.entities.keys():
            entities_dict[e] = self.entities[e].serialize(e)
        pack = dict()
        pack["rep"] = entities_dict
        return json.dumps(pack)
    
    def get_last_alive(self):
        for e in self.entities.keys():
            if not self.entities[e].eliminated:
                return e
    
    def count_alive_player(self):
        count = 0
        for i, j in self.entities.items():
            if not j.eliminated:
                count += 1
        return count

    def end_game(self) -> None:
        """Fini une partie avant d'en commencer une nouvelle"""
        last_standing = self.get_last_alive()
        self.server_connection.sendto_all_client(('{"win":'+str(last_standing)+'}').encode("utf-8"))
        self.client_addr = dict()
        self.entities = dict()
        self.game_start = time()
        self.next_net_id = 0
        self.state = ServerState.DIED
        self.running = False
        
        print("INFO: Stopping server")

    def load_maps(self):
        self.maps = list()
        directories = os.listdir("Map/Arenas")

        for directory in directories:
            filenames = next(os.walk("Map/Arenas/"+directory), (None, None, []))[2]
        for file in filenames:
            if file.endswith(".tmx"):
                tmxMap = Map("Map/Arenas/"+directory+"/"+file)
                tmxMap.name = file.removesuffix(".tmx")
                with open("Map/Arenas/" + directory + "/spawn_pos.json") as f:
                    content = f.read()
                    obj = json.loads(content)
                    tmxMap.spawn_position = obj.get("position")
                
                print(tmxMap.spawn_position)

                self.maps.append(tmxMap)
    
    def load_map_rects(self, tmx_data):
        coliders=[]



        windowXLimit = 400 - ((tmx_data.width / 2) * tmx_data.tilewidth )
        windowYLimit = 300 - ((tmx_data.height / 2) * tmx_data.tileheight)

        for layer in tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer):
                for x, y, tile in layer.tiles():

                    posX = (x*(tmx_data.tilewidth))+windowXLimit
                    posY = (y*(tmx_data.tileheight))+windowYLimit


                                        
                    scaledTile =  pygame.transform.scale(tile,(tmx_data.tilewidth, tmx_data.tileheight))
                    
                    tileRect = scaledTile.get_rect()
                    tileRect.x=posX
                    tileRect.y=posY
                    
                    coliders.append(tileRect)
        return coliders

def load_config(path):
    import jsonschema
    config_schema = {
        "properties": {
            "server_ip": {
                "type": "string"
            },
            "server_port": {
                "type": "integer"
            },
            "num_player": {
                "type": "integer"
            }
        },
        "required": ["server_ip", "server_port", "num_player"]
    }
    
    content = ""
    with open(path, "r") as f:
        content = f.read()
    try:
        json_obj = json.loads(content)
    except:
        print("Impossible de charger la configuration")
        exit(1)
    
    try:
        jsonschema.validate(json_obj, config_schema)
        return json_obj
    except Exception as e:
        print("Le fichier de configuration n'est pas valide")
        print(e)
        exit(1)

def load_config_from_env():
    return {
        "server_ip": os.getenv("SERVER_IP", "0.0.0.0"),
        "server_port": int(os.getenv("SERVER_PORT", "9999")),
            "num_player": int(os.getenv("SERVER_PLAYER", "4")),
    }

if __name__ == "__main__":
    if os.getenv("SERVER_CONFIG_FROM_FILE") is None:
        config = load_config("Config/server.json")
    else:
        config = load_config_from_env()
    server = Server(config)
    server.run()