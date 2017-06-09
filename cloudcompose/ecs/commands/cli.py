import click
from cloudcompose.ecs.controller import Controller
from cloudcompose.config import CloudConfig
from cloudcompose.exceptions import CloudComposeException


@click.group()
def cli():
    pass


@cli.command()
def up():
    """
    updates cluster configuration
    """
    try:
        cloud_config = CloudConfig()
        controller = Controller(cloud_config)
        controller.cluster_up()
    except CloudComposeException as ex:
        print(ex.message)


@cli.command()
@click.option('--force/--no-force', default=False, help="Force the cluster to go down even if terminate protection is enabled")
def down(force):
    """
    destroy ECS cluster
    """
    try:
        cloud_config = CloudConfig()
        controller = Controller(cloud_config)
        controller.cluster_down(force)
    except CloudComposeException as ex:
        print(ex.message)


@cli.command()
def health():
    """
    check ECS cluster health
    """
    try:
        cloud_config = CloudConfig()
        controller = Controller(cloud_config)
        name = cloud_config.config_data('cluster')['name']
        healthy = controller.cluster_health()
        if healthy:
            print("{} is healthy".format(name))
        else:
            print("{} is unhealthy".format(name))
    except CloudComposeException as ex:
        print(ex.message)


@cli.command()
@click.option('--single-step/--no-single-step', default=False, help="Perform only one upgrade step and then exit")
def upgrade(single_step):
    """
    upgrade the ECS cluster
    """
    try:
        cloud_config = CloudConfig()
        controller = Controller(cloud_config)
        controller.upgrade(single_step)
    except CloudComposeException as ex:
        print(ex.message)


@cli.command()
def cleanup():
    """
    deletes launch configs and auto scaling group
    """
    try:
        cloud_config = CloudConfig()
        controller = Controller(cloud_config)
        controller.cleanup()
    except CloudComposeException as ex:
        print(ex.message)
