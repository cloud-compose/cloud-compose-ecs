import click
from cloudcompose.ecs.controller import Controller
from cloudcompose.config import CloudConfig
from cloudcompose.exceptions import CloudComposeException


@click.group()
def cli():
    pass


@cli.command()
@click.option('--upgrade-image/--no-upgrade-image', default=False, help="Upgrade the image to the newest version instead of keeping the cluster consistent")
def up(upgrade_image):
    """
    updates cluster configuration
    """
    try:
        cloud_config = CloudConfig(upgrade_image=upgrade_image)
        controller = Controller(cloud_config)
        controller.cluster_up()
    except CloudComposeException as ex:
        print((ex.message))


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
        print((ex.message))


@cli.command()
@click.option('--verbose/--no-verbose', default=False, help="Output detailed health check information")
def health(verbose):
    """
    check ECS cluster health
    """
    try:
        cloud_config = CloudConfig()
        controller = Controller(cloud_config)
        name = cloud_config.config_data('cluster')['name']
        healthy = controller.cluster_health(verbose)
        if healthy:
            print(("{} is healthy".format(name)))
        else:
            print(("{} is unhealthy".format(name)))
    except CloudComposeException as ex:
        print((ex.message))


@cli.command()
@click.option('--single-step/--no-single-step', default=False, help="Perform only one upgrade step and then exit")
@click.option('--upgrade-image/--no-upgrade-image', default=True, help="Upgrade the image to the newest version instead of keeping the cluster consistent")
def upgrade(single_step, upgrade_image):
    """
    upgrade the ECS cluster
    """
    try:
        cloud_config = CloudConfig()
        controller = Controller(cloud_config, upgrade_image=upgrade_image)
        controller.upgrade(single_step)
    except CloudComposeException as ex:
        print((ex.message))


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
        print((ex.message))
