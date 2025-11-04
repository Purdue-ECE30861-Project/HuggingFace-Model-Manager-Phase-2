import botocore
import logging


class S3BucketManager:
    def __init__(self, endpoint_url: str = 'http://localhost:9000',
                 aws_access_key_id: str = 'minio_access_key_123',
                 aws_secret_access_key: str = 'minio_secret_key_password_456',
                 bucket_name: str = 'hfmm-artifact-storage',
                 data_prefix: str = 'artifacts/'):
        self.s3_client = botocore.session.get_session().create_client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        self.bucket_name = bucket_name
        self.data_prefix = data_prefix

    def s3_artifact_upload(self, artifact_id: str, content: bytes) -> None:
        """Upload artifact content to S3 bucket"""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"{self.data_prefix}{artifact_id}",
                Body=content
            )
        except Exception as e:
            logging.error(f"Error uploading artifact to S3: {e}")
            raise

    def s3_generate_presigned_url(self, artifact_id: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for direct client download"""
        return self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket_name, 'Key': f"{self.data_prefix}{artifact_id}"},
            ExpiresIn=expires_in
        )

    def s3_artifact_delete(self, artifact_id: str) -> None:
        """Delete artifact from S3 bucket"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=f"{self.data_prefix}{artifact_id}"
            )
        except Exception as e:
            logging.error(f"Error deleting artifact from S3: {e}")
            raise

    def s3_artifact_exists(self, artifact_id: str) -> bool:
        """Check if artifact exists in S3 bucket"""
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=f"{self.data_prefix}{artifact_id}"
            )
            return True
        except Exception:
            return False