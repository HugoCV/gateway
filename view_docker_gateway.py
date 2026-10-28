"""Open the existing Gateway desktop window against a local Docker container."""
import argparse

from ui.docker_viewer import DockerRuntimeClient
from ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="Ver un gateway Docker sin iniciar otro motor")
    parser.add_argument(
        "--container", default="alrotek-dev-gateway-1",
        help="Nombre del contenedor del gateway local",
    )
    args = parser.parse_args()
    client = DockerRuntimeClient(args.container)
    window = MainWindow(
        client=client, read_only=True,
        title="Puerta de enlace · Docker · {}".format(args.container),
    )
    window.mainloop()


if __name__ == "__main__":
    main()
