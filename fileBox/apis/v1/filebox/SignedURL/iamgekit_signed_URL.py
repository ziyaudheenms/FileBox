import os
from imagekitio import ImageKit
from dotenv import load_dotenv
from urllib.parse import urlparse
load_dotenv()
imagekit = ImageKit(
                private_key=os.getenv("IMAGEKIT_PRIVATE_KEY"),
                public_key=os.getenv("IMAGEKIT_PUBLIC_KEY"),
                url_endpoint=os.getenv("IMAGEKIT_URL_ENDPOINT")
            )


def generate_signed_url(url , expire_second = 3600):
    """
        Used to generate signed urls for accessing imagekit resources..........
    """

    #we have to extract the path from the url

    relative_path = urlparse(url).path
    clean_path = relative_path.replace(f"/{os.getenv('IMAGEKIT_ID')}/", "")


    signed_url = imagekit.url(
        {
        "path": clean_path,
        "signed": True,
        "expire_seconds": expire_second,
        # Optional: You can also add transformations here!
        "transformation": [
            # {"height": "800", "width": "1200", "quality": "80"}
        ]
    }
    )

    return signed_url

