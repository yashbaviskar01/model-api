@Library('jenkins-library') _

pipeline
{
  agent any
  stages
  {
    stage('Build preparations') {
      steps {
        script {
          gitCommitHash = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
          shortCommitHash = gitCommitHash.take(7)
          // calculate a sample version tag
          VERSION = shortCommitHash
          // set the build display name
          currentBuild.displayName = "#${BUILD_ID}-${VERSION}"
          if (env.BRANCH_NAME == 'dev') {
              IMAGE = "$PROJECT:dev-$VERSION"
          } else if (env.BRANCH_NAME == 'test') {
              IMAGE = "$PROJECT:test-$VERSION"
          } else if (env.BRANCH_NAME == 'main') {
              IMAGE = "$PROJECT:prod-$VERSION"
          }
        }

      }
    }

    stage('Docker build') {
      steps {
        script {
          docker.build("$IMAGE")
        }
      }
    }

    stage('Docker push') {
      steps {
        script {
          sh("aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${ECR}")
          ECRURL = "http://${ECR}"
          echo ECRURL
          // Push the Docker image to ECR
          docker.withRegistry(ECRURL)
          {
            docker.image(IMAGE).push()
          }
          echo TF_VAR_app_image
          TF_VAR_app_image = "${ECR}${IMAGE}"
          echo TF_VAR_app_image
        }

      }
    }

    stage('Deploy - Dev') {
      when {
        branch 'dev'
      }

      steps
      {
        git(url: 'https://bitbucket.org/exp-realty/exp-tf-dev.git', branch: 'master', credentialsId: 'exp-jenkins')
            withCredentials([[
              $class: 'AmazonWebServicesCredentialsBinding',
              accessKeyVariable: 'AWS_ACCESS_KEY_ID',
              secretKeyVariable: 'AWS_SECRET_ACCESS_KEY',
              credentialsId: 'Jenkins-Dev'
            ]]) {
            script
            {
              docker.image('204048894727.dkr.ecr.us-east-1.amazonaws.com/exp/jenkins-terraform')
                .inside("-u 0 -v $WORKSPACE:/data -v /var/lib/jenkins/.ssh:/data/.ssh -e BITBUCKET_USER=exp-jenkins -e AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} -e AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}")
                {
                  sh """
                  aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID --profile exp-dev
                  aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY --profile exp-dev
                  aws configure set region us-east-1 --profile exp-dev

                  cd account/exp-realty-dev/us-east-1/agent-platform/model-api-v2/ecs
                  terragrunt init -reconfigure
                  terragrunt plan --terragrunt-log-level trace -input=false -var 'image=${TF_VAR_app_image}'
                  terragrunt apply -auto-approve -input=false -var 'image=${TF_VAR_app_image}'
                  """
                }
            }
          }
        }
    }
    stage('Deploy - Qa') {
      when {
        branch 'test'
      }

      steps
      {
        git(url: 'https://bitbucket.org/exp-realty/exp-tf-qa.git', branch: 'master', credentialsId: 'exp-jenkins')
            withCredentials([[
              $class: 'AmazonWebServicesCredentialsBinding',
              accessKeyVariable: 'AWS_ACCESS_KEY_ID',
              secretKeyVariable: 'AWS_SECRET_ACCESS_KEY',
              credentialsId: 'jenkins-qa-user'
            ]]) {
            script
            {
              docker.image('204048894727.dkr.ecr.us-east-1.amazonaws.com/exp/jenkins-terraform')
                .inside("-u 0 -v $WORKSPACE:/data -v /var/lib/jenkins/.ssh:/data/.ssh -e BITBUCKET_USER=exp-jenkins -e AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} -e AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}")
                {
                  sh """
                  aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID --profile exp-qa
                  aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY --profile exp-qa
                  aws configure set region us-east-1 --profile exp-qa

                  cd /data/account/exp-realty-qa/us-east-1/agent-platform/model-api-v2/ecs
                  terragrunt init -reconfigure
                  terragrunt plan --terragrunt-log-level trace -input=false -var 'image=${TF_VAR_app_image}'
                  terragrunt apply -auto-approve -input=false -var 'image=${TF_VAR_app_image}'
                  """
                }
              }
            }
        }
      }
    stage('Deploy - Prod') {
      when {
        branch 'main'
      }

      steps
      {
        git(url: 'https://bitbucket.org/exp-realty/exp-tf-prod.git', branch: 'master', credentialsId: 'exp-jenkins')
            withCredentials([[
              $class: 'AmazonWebServicesCredentialsBinding',
              accessKeyVariable: 'AWS_ACCESS_KEY_ID',
              secretKeyVariable: 'AWS_SECRET_ACCESS_KEY',
              credentialsId: '88caba18-4691-47c5-92a9-e66ee83da4e4'
            ]]) {
            script
            {
              docker.image('204048894727.dkr.ecr.us-east-1.amazonaws.com/exp/jenkins-terraform')
                .inside("-u 0 -v $WORKSPACE:/data -v /var/lib/jenkins/.ssh:/data/.ssh -e BITBUCKET_USER=exp-jenkins -e AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} -e AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}")
                {
                  sh """
                  aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID --profile exp-production
                  aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY --profile exp-production
                  aws configure set region us-east-1 --profile exp-production

                  cd /data/account/exp-realty-prod/us-east-1/agent-platform/model-api-v2/ecs
                  terragrunt init -reconfigure
                  terragrunt plan --terragrunt-log-level trace -input=false -var 'image=${TF_VAR_app_image}'
                  terragrunt apply -auto-approve -input=false -var 'image=${TF_VAR_app_image}'
                  """
                }
          }
      }
    }
  }
  }
  environment {
    VERSION = 'latest'
    PROJECT = 'exp/agent-platform-model-api'
    IMAGE = 'exp/agent-platform-model-api:latest'
    ECRURL = ''
    TF_VAR_app_image = '99'
    ECR = '204048894727.dkr.ecr.us-east-1.amazonaws.com/'
    TF_LOG = 'ERROR'
    RECIPIENT_LIST = 'connor.reid@exprealty.net'
  }
  post {
    always {
      cleanWs()
      sh "docker rmi $IMAGE | true"
    }
    success {
      script {
        CommonPostStepSuccess()
      }
    }
    failure {
      script {
        CommonPostStepFailure()
      }
    }
  }
  options {
    buildDiscarder(logRotator(numToKeepStr: '3'))
  }
}
