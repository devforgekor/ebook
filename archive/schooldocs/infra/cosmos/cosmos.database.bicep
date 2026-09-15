// infra/cosmos/cosmos.database.bicep
targetScope = 'resourceGroup'

param sharedCosmosAccountName string
param cosmosDatabaseName string
param cosmosContainerName string

resource sharedCosmos 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' existing = {
  name: sharedCosmosAccountName
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-04-15' = {
  name: cosmosDatabaseName
  parent: sharedCosmos
  properties: {
    resource: { id: cosmosDatabaseName }
  }
}

resource recordsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2023-04-15' = {
  name: cosmosContainerName
  parent: cosmosDatabase
  properties: {
    resource: {
      id: cosmosContainerName
      conflictResolutionPolicy: {
        mode: 'LastWriterWins'
        conflictResolutionPath: '/_ts'
      }
      partitionKey: {
        paths: [ '/cohortId' ]
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        excludedPaths: [
          { path: '/"_etag"/?' }
        ]
        includedPaths: [
          { path: '/*' }
          { path: '/cohortId/?' }
          { path: '/personKey/?' }
          { path: '/type/?' }
        ]
        compositeIndexes: [
          [
            { path: '/cohortId', order: 'ascending' }
            { path: '/personKey', order: 'ascending' }
            { path: '/type', order: 'ascending' }
          ]
        ]
      }
    }
  }
}
