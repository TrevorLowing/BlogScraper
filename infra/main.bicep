@description('Azure region for all resources in this deployment.')
param location string = resourceGroup().location

@description('Globally unique base string; default is derived from RG + subscription.')
param nameSuffix string = take(uniqueString(resourceGroup().id, subscription().subscriptionId), 13)

@description('Use Y1/Dynamic (Consumption) when your subscription has quota; many subs need Basic (B1) first.')
@allowed(['Dynamic', 'Basic'])
param hostPlan string = 'Basic'

@description('Disable if Microsoft.OperationalInsights is not registered on the subscription yet.')
param enableAppInsights bool = false

@description('Optional Key Vault reference for TRANSLATOR_KEY app setting.')
param translatorKeyReference string = ''

var storageAccountName = toLower('blogst${nameSuffix}')
var functionAppName = 'blogscrapr-${toLower(nameSuffix)}'
var hostingPlanName = 'blogscrap-${toLower(nameSuffix)}'
var appInsightsName = 'blogscrap-ai-${take(nameSuffix, 10)}'
var contentShareName = toLower(replace(functionAppName, '-', ''))

var storageConnString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'Storage'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: 'default'
  parent: storageAccount
}

resource blogContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'blog-scraper'
  properties: {
    publicAccess: 'None'
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = if (enableAppInsights) {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    Flow_Type: 'Bluefield'
    Request_Source: 'rest'
    RetentionInDays: 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource hostingPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: hostingPlanName
  location: location
  sku: hostPlan == 'Dynamic'
    ? {
        name: 'Y1'
        tier: 'Dynamic'
      }
    : {
        name: 'B1'
        tier: 'Basic'
        size: 'B1'
        family: 'B'
        capacity: 1
      }
  properties: {
    reserved: true
  }
}

var appInsightsConnectionString = enableAppInsights ? applicationInsights!.properties.ConnectionString : ''
var translatorKeyAppSettingValue = empty(translatorKeyReference) ? '' : translatorKeyReference

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    httpsOnly: true
    serverFarmId: hostingPlan.id
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      alwaysOn: hostPlan == 'Basic'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: storageConnString
        }
          {
            name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING'
            value: storageConnString
          }
          {
            name: 'WEBSITE_CONTENTSHARE'
            value: contentShareName
          }
          {
            name: 'FUNCTIONS_EXTENSION_VERSION'
            value: '~4'
          }
          {
            name: 'FUNCTIONS_WORKER_RUNTIME'
            value: 'python'
          }
          {
            name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
            value: appInsightsConnectionString
          }
          {
            name: 'APPLICATIONINSIGHTS_ENABLE_AGENT'
            value: enableAppInsights ? 'true' : 'false'
          }
          {
            name: 'BLOG_SCRAPER_STORAGE'
            value: storageConnString
          }
          {
            name: 'BLOB_CONTAINER_NAME'
            value: 'blog-scraper'
          }
          {
            name: 'BLOG_SITE_BASE'
            value: 'https://www.yidaiyilu.gov.cn'
          }
          {
            name: 'BLOG_INDEX_PATH'
            value: '/list/w/xmzb'
          }
          {
            name: 'HTTP_USER_AGENT'
            value: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
          }
          {
            name: 'HTTP_EXTRA_HEADERS_JSON'
            value: '{}'
          }
          {
            name: 'CONTENT_SELECTORS'
            value: '.news-news-box,.news-details-content'
          }
          {
            name: 'SCRAPER_TIMER_SCHEDULE'
            value: '0 0 10 * * *'
          }
          {
            name: 'TRANSLATOR_ENDPOINT'
            value: ''
          }
          {
            name: 'TRANSLATOR_KEY'
            value: translatorKeyAppSettingValue
          }
          {
            name: 'TRANSLATOR_REGION'
            value: ''
          }
          {
            name: 'BLOG_HTML_EXCLUDE_PATHS'
            value: '/p/178715.html'
          }
          {
            name: 'ACI_USE_MANAGED_IDENTITY_PULL'
            value: 'true'
          }
      ]
    }
  }
}

output functionAppName string = functionApp.name
output functionAppHostName string = functionApp.properties.defaultHostName
output storageAccountName string = storageAccount.name
output appInsightsName string = enableAppInsights ? applicationInsights!.name : ''
