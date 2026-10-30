# mlops-aws-pipeline

**New study project, in progress.** I am building an end-to-end MLOps pipeline on AWS from scratch, writing the code myself to learn each piece.

## Plan

1. Daily ETL of a public dataset into S3
2. Training a classical model with versioned runs and metrics
3. Deploying the model as an API
4. Monitoring predictions against actuals, with retraining on drift
5. CI on GitHub with tests

Everything runs on the AWS free tier, with a cost alert from day one. Nothing here is production-grade yet; this README will track what is done.
