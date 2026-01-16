def example_node_specific():
    """Client sends only to local DMS"""
    from trilio_dms import DMSClient
    import socket
    # Get local node ID
    node_id = socket.gethostname()  # e.g., 'compute-01'
    # Create client (automatically uses local node)
    client = DMSClient(
        rabbitmq_url='amqp://openstack:BApTSybZfXrqoW4c867ngetJlxTrAbVvvOjKP5r6@172.26.0.8:5672/',
        wait_for_response=False,
        node_id=node_id  # Optional, auto-detected
    )
    token = "gAAAAABpZjktjK8mXU7_QHLqUXHhGxYINVzJF_0jnzCW1hOhpWINaM8QunRTcuQRMknVQSX0RAn7gIfHm0dpiYArKfaS7RWPArk9c2g-bqiDSO8MHUEV0zPmD3Nm88YWvNKrQRXscC9SqAkF1bv1DJKVauAVWrjkKa3QQ9NYR1IQfeJczs6tmyk"
    # This sends to queue: trilio_dms_ops_compute-01
    client.mount(1, '20272009-8408-4f3f-97eb-bff61c3c5712', token)
    # Only DMS server on compute-01 will process this
    client.close()
example_node_specific()
