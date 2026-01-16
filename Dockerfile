DOCKERFILE = """FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    s3fs \\
    fuse \\
    nfs-common \\
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /opt/trilio/dms /run/dms/s3 /var/log/trilio /mnt/trilio

# Set working directory
WORKDIR /opt/trilio/dms

# Copy package
COPY . .

# Install Python package
RUN pip install --no-cache-dir .

# Expose health check port
EXPOSE 8080

# Run as root (needed for mounts)
USER root

# Entry point
CMD ["trilio-dms"]
"""

