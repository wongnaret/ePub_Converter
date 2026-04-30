import eventlet
eventlet.monkey_patch()

from app import app, socketio

if __name__ == '__main__':
    print("Starting Flask-SocketIO server with Eventlet...")
    # Running with debug=True will use the Flask reloader, which is now safe
    # because this script ensures the patch is applied before the app is imported.
    socketio.run(app, port=5000, debug=True)
