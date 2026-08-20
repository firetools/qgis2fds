<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis hasScaleBasedVisibilityFlag="0" styleCategories="AllStyleCategories" version="3.20.2-Odense" maxScale="0" minScale="1e+08">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>0</Searchable>
    <Private>0</Private>
  </flags>
  <temporal enabled="0" fetchMode="0" mode="0">
    <fixedRange>
      <start></start>
      <end></end>
    </fixedRange>
  </temporal>
  <customproperties>
    <Option type="Map">
      <Option value="false" name="WMSBackgroundLayer" type="QString"/>
      <Option value="false" name="WMSPublishDataSourceUrl" type="QString"/>
      <Option value="0" name="embeddedWidgets/count" type="QString"/>
      <Option value="Value" name="identify/format" type="QString"/>
    </Option>
  </customproperties>
  <pipe>
    <provider>
      <resampling zoomedInResamplingMethod="nearestNeighbour" maxOversampling="2" enabled="false" zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer alphaBand="-1" nodataColor="" opacity="1" band="1" type="paletted">
      <rasterTransparency/>
      <minMaxOrigin>
        <limits>None</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <colorPalette>
        <paletteEntry color="#ffffff" value="0" alpha="255" label="NA"/>
        <paletteEntry color="#ba5f00" value="1" alpha="255" label="Broadleaves"/>
        <paletteEntry color="#e90000" value="2" alpha="255" label="Shrubs"/>
        <paletteEntry color="#000000" value="3" alpha="0" label="No Vegetation"/>
        <paletteEntry color="#00eb00" value="4" alpha="255" label="Grass"/>
        <paletteEntry color="#e6eb00" value="5" alpha="255" label="Mediterranean Conifer"/>
        <paletteEntry color="#2a70c4" value="6" alpha="255" label="Crops"/>
        <paletteEntry color="#5d3200" value="7" alpha="255" label="Non fire-prone Veg."/>
      </colorPalette>
      <colorramp name="[source]" type="gradient">
        <Option type="Map">
          <Option value="215,25,28,255" name="color1" type="QString"/>
          <Option value="43,131,186,255" name="color2" type="QString"/>
          <Option value="0" name="discrete" type="QString"/>
          <Option value="gradient" name="rampType" type="QString"/>
          <Option value="0.25;253,174,97,255:0.5;255,255,191,255:0.75;171,221,164,255" name="stops" type="QString"/>
        </Option>
        <prop k="color1" v="215,25,28,255"/>
        <prop k="color2" v="43,131,186,255"/>
        <prop k="discrete" v="0"/>
        <prop k="rampType" v="gradient"/>
        <prop k="stops" v="0.25;253,174,97,255:0.5;255,255,191,255:0.75;171,221,164,255"/>
      </colorramp>
    </rasterrenderer>
    <brightnesscontrast gamma="1" contrast="0" brightness="0"/>
    <huesaturation colorizeOn="0" colorizeGreen="128" grayscaleMode="0" colorizeStrength="100" saturation="0" colorizeBlue="128" colorizeRed="255"/>
    <rasterresampler maxOversampling="2"/>
    <resamplingStage>resamplingFilter</resamplingStage>
  </pipe>
  <blendMode>6</blendMode>
</qgis>
