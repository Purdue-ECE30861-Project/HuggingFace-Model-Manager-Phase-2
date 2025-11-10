import boto3
import botocore.exceptions as botoexc
import logging
from pathlib import Path


class S3BucketManager:
    def __init__(self, endpoint_url: str = 'http://localhost:9000',
                 aws_access_key_id: str = 'minio_access_key_123',
                 aws_secret_access_key: str = 'minio_secret_key_password_456',
                 bucket_name: str = 'hfmm-artifact-storage',
                 data_prefix: str = 'artifacts/',
                 region_name: str = None
        ):
        self.s3_client = boto3.client(
            's3',
            region_name=region_name,
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        print(self.s3_client.list_buckets())
        self.bucket_name = bucket_name
        self.data_prefix = data_prefix

    def s3_artifact_upload(self, artifact_id: str, filepath: Path) -> None:
        """Upload artifact content to S3 bucket"""
        try:
            self.s3_client.upload_file(filepath, self.bucket_name, f"{self.data_prefix}{artifact_id}")
        except botoexc.ClientError as e:
            logging.error(f"Error uploading artifact to S3: {e}")
            raise

    def s3_artifact_download(self, artifact_id: str, filepath: Path):
        try:
            self.s3_client.download_file(self.bucket_name, f"{self.data_prefix}{artifact_id}", filepath)
        except botoexc.ClientError as e:
            logging.error(f"Error downloading artifact from s3: {e}")
            raise

    def s3_generate_presigned_url(self, artifact_id: str, expires_in: int = 3600) -> str | None:
        """Generate presigned URL for direct client download""" # good for now but spec demands to be able to pick and choose elemnts to download
        try:
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': f"{self.data_prefix}{artifact_id}"},
                ExpiresIn=expires_in
            )
        except botoexc.ClientError as e:
            logging.error(f"Error generating presigned url from s3: {e}")

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
        
    def s3_reset(self) -> None:
        """Delete all objects from the S3 bucket."""
        try:
            # List all objects in the bucket
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.data_prefix
            )
            
            if 'Contents' in response:
                # Create list of objects to delete
                delete_list = {'Objects': [{'Key': obj['Key']} for obj in response['Contents']]}
                
                # Delete all objects if any exist
                if delete_list['Objects']:
                    self.s3_client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete=delete_list
                    )
                    logging.info(f"Deleted {len(delete_list['Objects'])} objects from bucket {self.bucket_name}")
        except Exception as e:
            logging.error(f"Error resetting S3 bucket: {e}")
            raise