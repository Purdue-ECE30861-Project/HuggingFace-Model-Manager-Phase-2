from __future__ import annotations
from abc import ABC, abstractmethod
from typing_extensions import override, Literal, Any
from pydantic import BaseModel, HttpUrl
import sqlite3
from pathlib import Path
import mysql.connector
import dotenv
import os

class MetricResult(BaseModel):
    name: str
    score: float = 0
    latency: int = 0


class ModelData(BaseModel):
    model_name: str
    model_url: HttpUrl
    dataset_url: HttpUrl
    codebase_url: HttpUrl
    metrics: list[MetricResult]


class SQLAccessor(ABC):

    db_path: Path | Literal[":memory:"]
    schema: ModelData
    primary_key: str
    static_headers: list[str]
    metric_headers: list[tuple[str, str]]
    flattened_metric_headers: list[str]
    flattened_headers: list[str]

    def __init__(self, schema: ModelData, db_path: Path | Literal[":memory:"]=":memory:", primary_key: str="model_url") -> None:
        self.schema = schema
        self.primary_key = primary_key
        self.db_path = db_path
        self.setup_connection()
        self.create_database()

        return super().__init__()

    def __del__(self):
        self.close_connection()
    
    def create_database(self):
        """
        create a database if it does not exist or does not match the provided schema
        """
        self.static_headers = [header for header in dict(self.schema).keys() if header != "metrics"]
        if self.primary_key not in self.static_headers:
            raise ValueError("Primary key not present in database schema")
        self.static_headers.remove(self.primary_key)
        self.metric_headers = [(metric.name, metric.name + "_latency") for metric in self.schema.metrics]
        schema_descriptor = f"{self.primary_key} TEXT PRIMARY KEY, " + ", ".join([f"{name} TEXT" for name in self.static_headers]) + ", " + ", ".join([f"{metric} FLOAT, {latency} INT" for metric, latency in self.metric_headers])
        self.execute(f"CREATE TABLE IF NOT EXISTS models ({schema_descriptor})", [])
        
        # create list of flattened headers for ease of use with SQL queries
        self.flattened_metric_headers = [header for metric in self.metric_headers for header in metric]
        self.headers: list[str] = [self.primary_key]
        self.headers.extend(self.static_headers)
        self.headers.extend(self.flattened_metric_headers)
    
    def insert_model(self, data: ModelData):
        """
        insert a model into the database
        Parameters:
            data: ModelData of metric results, URLs, and model name
        """
        # check for matching schema
        if [metric.name for metric in self.schema.metrics] != [metric.name for metric in self.schema.metrics]:
            raise ValueError("model data does not match database schema")

        model_values: list[str] = [dict(data)[self.primary_key]]
        model_values.extend([str(dict(data)[header]) for header in self.static_headers])
        model_values.extend([str(dict(data)["metrics"][header]) for header in self.flattened_metric_headers])

        self.execute(f"INSERT INTO models ({', '.join(self.headers)}) VALUES ({', '.join(['?' for _ in model_values])})", model_values)
    
    def fetch_model_info(self, primary_key_value: str) -> ModelData|None:
        """
        get stored information about a model if it exists
        Parameters:
            primary_key_value: value of the pre-defined database primary key
        Returns:
            structured_data: 
        
        """
        new_data = self.execute_and_fetchone(f"SELECT {', '.join(self.flattened_headers)} FROM models WHERE {self.primary_key} = ?", [primary_key_value])
        if new_data is None:
            return None
        
        # yeah i have literally no idea how to make this adapt dynamically to changes in ModelData
        structured_data = ModelData(model_name=new_data.pop(), model_url=new_data.pop(), dataset_url=new_data.pop(), codebase_url=new_data.pop(), metrics = [])
        structured_data.metrics = [MetricResult(name=metric, score=new_data.pop(), latency=new_data.pop()) for metric in self.flattened_metric_headers]
        return structured_data
        


    @abstractmethod
    def setup_connection(self):
         """
        set up the connection to the database
        """
         
    @abstractmethod
    def close_connection(self):
         """
        commit and close the connection to the database
        """

    @abstractmethod
    def execute_and_fetchall(self, query: str, parameters: list[str]) -> list[list[Any]]|None:
        """
        execute an SQL query and return all matching rows.
        Parameters:
            query: sql query to run
            parameters: list of parameters to the query
        Returns: 
            A list of database rows matching the query
        """
        ...

    @abstractmethod
    def execute_and_fetchone(self, query: str, parameters: list[str]) -> list[Any]|None:
        """
        execute an SQL query and return the first matching row.
        Parameters:
            query: sql query to run
            parameters: list of parameters to the query 
        Returns: 
            The first database rows matching the query
        """
        ...
    
    @abstractmethod
    def execute(self, query: str, parameters: list[str]):
        """
        execute an SQL query without returning anything.
        Parameters:
            query: sql query to run
            parameters: list of parameters to the query
        """
        ...

class MySQLAccessor(SQLAccessor):
    @override
    def setup_connection(self):
        """
        set up the connection to the database
        """
        dotenv.load_dotenv()
        self.connection = mysql.connector.connect(host="127.0.0.1", user=os.getenv("MYSQL_USERNAME"), passwd=os.getenv("MYSQL_PASSWD"), database=self.db_path)
        self.cursor = self.connection.cursor()

         
    @override
    def close_connection(self):
         """
        commit and close the connection to the database
        """
         self.connection.commit()
         self.connection.close()
         

    @override
    def execute_and_fetchall(self, query: str, parameters: list[str]) -> list[list[Any]]|None:
        """
        execute an SQL query and return all matching rows.
        Parameters:
            query: sql query to run
        Returns: 
            A list of database rows matching the query
        """
        self.cursor.execute(query, tuple(parameters))
        self.cursor.fetchall()
        return self.cursor.fetchall() # pyright: ignore[reportReturnType]

    @override
    def execute_and_fetchone(self, query: str, parameters: list[str]) -> list[Any]|None:
        """
        execute an SQL query and return the first matching row.
        Parameters:
            query: sql query to run 
        Returns: 
            The first database rows matching the query
        """
        self.cursor.execute(query, tuple(parameters))
        return self.cursor.fetchone() # pyright: ignore[reportReturnType]
    
    @override
    def execute(self, query: str, parameters: list[str]):
        """
        execute an SQL query without returning anything.
        Parameters:
            query: sql query to run
        """
        self.cursor.execute(query, tuple(parameters))
        
        

class SQLiteAccessor(SQLAccessor):
    @override
    def setup_connection(self):
        """
        set up the connection to the database
        """
        self.connection = sqlite3.Connection(self.db_path)
        self.cursor = self.connection.cursor()
         
    @override
    def close_connection(self):
         """
        commit and close the connection to the database
        """
         self.connection.commit()
         self.connection.close()

    @override
    def execute_and_fetchall(self, query: str, parameters: list[str]) -> list[list[Any]]|None:
        """
        execute an SQL query and return all matching rows.
        Parameters:
            query: sql query to run
        Returns: 
            A list of database rows matching the query
        """
        self.cursor.execute(query, tuple(parameters))
        return self.cursor.fetchall()

    @override
    def execute_and_fetchone(self, query: str, parameters: list[str]) -> list[Any]|None:
        """
        execute an SQL query and return the first matching row.
        Parameters:
            query: sql query to run 
        Returns: 
            The first database rows matching the query
        """
        self.cursor.execute(query, tuple(parameters))
        return self.cursor.fetchone()
    
    @override
    def execute(self, query: str, parameters: list[str]):
        """
        execute an SQL query without returning anything.
        Parameters:
            query: sql query to run
        """
        self.cursor.execute(query, tuple(parameters))
    





