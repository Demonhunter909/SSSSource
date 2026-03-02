# SSSSource

This Flask application hosts a simple media upload service with a slideshow
and basic user management. It was developed for deployment on services such as
Render and includes support for persisting uploaded images either to a
mounted disk or to an S3 bucket.

## Deployment considerations

### Render.com

Render's containers use an *ephemeral* filesystem. Any files written to disk
will be lost when the service restarts or is redeployed. To store images
persistently you have two options:

1. **Attach a persistent disk.**
   - Render mounts disks under `/mnt/data` by default.
   - Set the `UPLOAD_FOLDER` environment variable to point at a folder on the
     disk (e.g. `/mnt/data/uploads`). The application will create the
     directory automatically.
   - The code also autodetects Render by checking for the
     `RENDER_INTERNAL_HOSTNAME` environment variable and will default to
     `/mnt/data/uploads` if `UPLOAD_FOLDER` isn't provided.
   - Disks are billed per GB-month, so this does incur cost.

2. **Use an external storage service (S3, Cloudinary, etc.).**
   - Provide the usual AWS env vars (`S3_BUCKET`, `AWS_ACCESS_KEY_ID`, etc.)
     and the app will upload images to S3 instead of the local filesystem.
   - This avoids paying Render for disk space but may still cost you on the
     storage provider.

### Other hosts

- The `UPLOAD_FOLDER` environment variable works on any platform; simply
  point it to a directory that the app can write to. The code creates the
  directory if it does not yet exist.
- For local development you can omit `UPLOAD_FOLDER` and uploads will be
  stored in `./uploads` within the project.

## Features

- Image uploads with secure filenames.
- Relational database tables for uploads, users, slideshow metadata, etc.
- Automatic session management, login/registration flow.
- Admin panel for managing slideshow images, including delete
  functionality.
- Optional AWS S3-backed storage via `boto3`.

Refer to the source code comments for further implementation details.