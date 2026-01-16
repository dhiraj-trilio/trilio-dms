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
    token="gAAAAABpZ0eVbyeRFxYB7MISkf-703WUs4JerKxNDWcHpvCWpIf51GnZ7wPU7EJIrhWM7RdtqnSzj9iLcFXUoY4_p7uKEmCEYca76dNtszjhBW8Dcj6SCElsogW_PNtbE4JkVkiRFLWlJsjHk-Xdl-jiiE1CfqGMDHDqRHn6rdXcvZBLe5E8MKQ"
    # This sends to queue: trilio_dms_ops_compute-01
    client.mount(1, '62b25699-c54e-4064-92db-fc94e36522b1', token)
    # Only DMS server on compute-01 will process this
    client.close()
example_node_specific()
