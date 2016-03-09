from flask import Flask, render_template, request
from flask_socketio import SocketIO, send, emit
from datetime import datetime as time
from math import cos, sin, tan, pi

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

if not app.debug:
    import logging
    file_handler = logging.FileHandler('error.log')
    file_handler.setLevel(logging.WARNING)
    app.logger.addHandler(file_handler)


class Game(object):
    WIDTH = 600
    HEIGHT = 400

    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.player1.x = Player.LEFT
        self.player2.x = Player.RIGHT
        self.ball = Ball(self)
        self.player1.game = self
        self.player2.game = self
        self.time = time.now()
        self.serve = 1

    def __iter__(self):
        yield ('player1', dict(self.player1))
        yield ('player2', dict(self.player2))
        yield ('ball', dict(self.ball))
        yield ('serve', self.serve)
        
    def _frame_count(self):
        delta = time.now() - self.time
        return (delta.days*24*60*60*1000 + delta.seconds*1000 + delta.microseconds / 1000) / 30
        
    def _reset_time(self):
        self.time = time.now()
        
    def _check_game(self):
        if self.ball.x + self.ball.w < 0:
            self.player2.score += 1
            self.serve = 1
        if self.ball.x > Game.WIDTH:
            self.player1.score += 1
            self.serve = 2

    def do_serve(self, player):
        if player == self.player1 and self.serve == 1:
            self.serve = 0
            self.ball.v = Ball.VELOCITY
            print("do_serve")
        if player == self.player2 and self.serve == 2:
            self.serve = 0
            self.ball.v = Ball.VELOCITY
            print("do_serve")
            
    def do_update(self):
        fc = self._frame_count()
        self._reset_time()
        for i in range(0, fc):
            self.player1.update(self)
            self.player2.update(self)
            self.ball.update(self)
            self._check_game()

    def broadcast(self, event, data=None):
        self.player1.emit(event, data)
        self.player2.emit(event, data)

    def emit_start(self):
        self.broadcast('game_start', data=dict(game=dict(self), user1=self.player1.username, user2=self.player2.username))

    def emit_update(self):
        self.broadcast("game_update", data=dict(game=dict(self)))    


class Player(object):
    WIDTH = 10
    HEIGHT = 70
    LEFT = 10
    RIGHT = Game.WIDTH-10-WIDTH
    TOP = 20
    VELOCITY = 5
    
    def __init__(self, username, sid=None):
        self.username = username
        self.x = Player.LEFT
        self.y = Player.TOP
        self.w = Player.WIDTH
        self.h = Player.HEIGHT
        self.v = Player.VELOCITY
        self.move = 0
        self.score = 0
        self.sid = sid

    def __iter__(self):
        yield ('x', self.x)
        yield ('y', self.y)
        yield ('w', self.w)
        yield ('h', self.h)
        yield ('v', self.v)
        yield ('move', self.move)
        yield ('score', self.score)        
            
    def update(self, game):
        self.y += self.v * self.move;
        # Stop pad at sidelines
        if self.y < 0:
            self.y = 1
        if self.y + self.h >= Game.HEIGHT:
            self.y = Game.HEIGHT - self.h - 1

    def emit(self, event, data=None):
        emit(event, data, room=self.sid)


class AIPlayer(Player):
    def __init__(self):
        super(AIPlayer, self).__init__('AI')
        self.y = 150

    def __iter__(self):
        yield ('x', self.x)
        yield ('y', self.y)
        yield ('w', self.w)
        yield ('h', self.h)
        yield ('v', self.v)
        yield ('move', self.move)
        yield ('score', self.score)
        yield ('ai', True)
        
    def update(self, game):
        bx = game.ball.x
        by = game.ball.y
        ba = game.ball.a % (2 * pi)
        ba = ba * 360 / 2 / pi
        if (ba > 0 and ba < 90) or (ba > 270 and ba < 360) or (ba < 0 and ba > -90):
            final_yf = by + (self.x - bx) * tan(pi * ba / 180)
            final_y = abs(final_yf)
            odd = int(final_y / (Game.HEIGHT-20)) & 1
            final_y %= (Game.HEIGHT-20)
            final_y = (Game.HEIGHT - 10) if odd else (10 + final_y)
            if (self.y + self.h / 2) < final_y:
                self.y += 5
            if (self.y + self.h / 2) > final_y:
                self.y -= 5
        super(AIPlayer, self).update(game)

    def emit(self, event, data=None):
        pass
        
        
class Ball(object):
    WIDTH = 10
    HEIGHT = 10
    VELOCITY = 10
    
    LEFT = Player.LEFT + Player.WIDTH + WIDTH
    RIGHT = Player.RIGHT - 2*WIDTH
    
    def __init__(self, game):
        self.game = game
        self.x = Player.LEFT
        self.y = Player.TOP
        self.w = Ball.WIDTH
        self.h = Ball.HEIGHT 
        self.v = 0
        self.a = pi / 3; 

    def __iter__(self):
        yield ('x', self.x)
        yield ('y', self.y)
        yield ('w', self.w)
        yield ('h', self.h)
        yield ('a', self.a)
        yield ('v', self.v)
            
    def update(self, game):
        if game.serve == 1:
            self.x = Ball.LEFT
            self.y = game.player1.y
            self.v = 0 
            return
        if game.serve == 2:
            self.x = Ball.RIGHT
            self.y = game.player2.y
            self.v = 0 
            return
            
        self.v  = Ball.VELOCITY
        self.x += self.v * cos(self.a)
        self.y += self.v * sin(self.a)
        # Reflect ball at sidelines
        if self.y < 0:
            self.a = 2*pi - self.a
        if self.y + self.h > Game.HEIGHT: 
            self.a = 2*pi - self.a
        # Reflect ball at players
        if self.collides(self.game.player1):
            self.a = pi - self.a
        if self.collides(self.game.player2):
            self.a = pi - self.a

    def collides(self, player):
        l1 = self.x - 5
        r1 = self.x + self.w + 5
        t1 = self.y - 5
        b1 = self.y + self.h + 5

        l2 = player.x
        r2 = player.x + player.w
        t2 = player.y
        b2 = player.y + player.h
            
        if l1 > r2:
		    return False
        if r1 < l2:
		    return False
        if t1 > b2:
		    return False
        if b1 < t2:
	        return False
        return True
        
            
games = {}
players = {}

@app.route('/') 
def index():
    return render_template('index.html') 

@socketio.on('connect')
def handle_connect():
    pass

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in players:
        del players[request.sid]
    if request.sid in games:
        game = games[request.sid]
        game.broadcast('game_disconnect')
        del games[request.sid]

@socketio.on('signup')
def handle_signup(json):
    players[request.sid] = Player(json['username'], request.sid)
    emit('signed_up', json)

@socketio.on('challenge_ai')
def handle_challenge_ai():
    player = players[request.sid]
    games[request.sid] = game = Game(player, AIPlayer())
    game.emit_start()

@socketio.on('move')
def handle_move(json):
    game = games[request.sid]
    game.do_update()
    player = players[request.sid]
    player.move = json['direction']
    game.emit_update()

@socketio.on('ball')
def handle_ball():
    game = games[request.sid]
    game.do_update()
    game.emit_update()

@socketio.on('serve')
def handle_serve():
    game = games[request.sid]
    game.do_serve(players[request.sid])
    game.do_update()
    game.emit_update()

@socketio.on('serve_ai')
def handle_serve_ai():
    game = games[request.sid]
    game.do_serve(game.player2)
    game.do_update()
    game.emit_update()

if __name__ == '__main__':
    socketio.run(app)
