def get_scoped_token():
    """Get a properly scoped Keystone token with service catalog."""
    from keystoneauth1.identity import v3
    from keystoneauth1 import session
    
    auth = v3.Password(
        auth_url='https://kolla-internal-rockycaracaldev3.triliodata.demo:5000',
        username='cloudadmin',
        password='password',
        project_name='cloudproject',
        user_domain_name='clouddomain',
        project_domain_name='clouddomain'
    )
    
    sess = session.Session(auth=auth, verify=False)
    
    # This token will have a service catalog
    token = sess.get_token()
    return token, sess
print(get_scoped_token())
