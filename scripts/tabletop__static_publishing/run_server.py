import os, json, time, signal, sys
os.environ['SEND__STORAGE_MODE'] = 'memory'
from sgraph_ai_app_send.lambda__user.testing.Send__User_Lambda__Test_Server import setup__send_user_lambda__test_server
with setup__send_user_lambda__test_server() as t:
    info = {'server_url': t.server_url, 'access_token': str(t.access_token)}
    with open(os.path.join(os.path.dirname(__file__), 'server.json'), 'w') as f:
        json.dump(info, f)
    print('SERVER READY', json.dumps(info), flush=True)
    signal.pause()
