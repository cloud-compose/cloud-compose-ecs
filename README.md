# Cloud Compose ECS plugin

The Cloud Compose ECS plugin simplifies management of [AWS ECS](https://aws.amazon.com/ecs/) clusters.

For an example ECS cluster using Cloud Compose, see [Docker ECS](https://github.com/washingtonpost/docker-ecs) .

Cloud Compose ECS supports the standard Cloud Compose Cluster commands, such as `up` and `down`.

## Installation

```bash
pip install cloud-compose-ecs
```

## Commands

### `upgrade`

Once you have a running ECS cluster using the [Cloud Compose Cluster](https://github.com/cloud-compose/cloud-compose-cluster) plugin,
use the following command to upgrade the cluster:

```bash
cloud-compose ecs upgrade
```

The upgrade command will make sure that your ECS cluster is healthy before starting the upgrade.
It will replace each instance within your ECS cluster and wait to ensure that services are
healthy before moving to the next instance.

### `health`

The health command checks if the ECS cluster is healthy by checking whether:

- the ECS cluster is active and available to accept new services/tasks
- services running on the cluster are active
- load balancers associated with services are healthy
- the number of registered container instances match the desired instances registered to the auto-scaling group

```bash
cloud-compose ecs health
```

The `--verbose` flag optionally enables detailed information about which services or load balancers are unhealthy.