uint8 OPEN=1
uint8 WRITE=2
uint8 READ=3
uint8 END=4
uint8 PROVIDE=5
uint8 operation
uint8 peer_id
string bits
# Caller correlation ID; for PROVIDE use the DATA_REQUEST event's request_id.
string request_id
