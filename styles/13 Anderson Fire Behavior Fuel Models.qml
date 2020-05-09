<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis maxScale="0" hasScaleBasedVisibilityFlag="0" minScale="1e+08" version="3.10.4-A Coruña" styleCategories="AllStyleCategories">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>0</Searchable>
  </flags>
  <customproperties>
    <property key="WMSBackgroundLayer" value="false"/>
    <property key="WMSPublishDataSourceUrl" value="false"/>
    <property key="embeddedWidgets/count" value="0"/>
    <property key="identify/format" value="Value"/>
  </customproperties>
  <pipe>
    <rasterrenderer type="paletted" alphaBand="-1" opacity="1" band="1">
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
        <paletteEntry color="#ffffff" label="NO_DATA" value="0" alpha="255"/>
        <paletteEntry color="#fffed4" label="FBFM01" value="1" alpha="255"/>
        <paletteEntry color="#fffd66" label="FBFM02" value="2" alpha="255"/>
        <paletteEntry color="#ecd463" label="FBFM03" value="3" alpha="255"/>
        <paletteEntry color="#fec177" label="FBFM04" value="4" alpha="255"/>
        <paletteEntry color="#f9c55c" label="FBFM05" value="5" alpha="255"/>
        <paletteEntry color="#d9c498" label="FBFM06" value="6" alpha="255"/>
        <paletteEntry color="#aa9b7f" label="FBFM07" value="7" alpha="255"/>
        <paletteEntry color="#e5fdd6" label="FBFM08" value="8" alpha="255"/>
        <paletteEntry color="#a2bf5a" label="FBFM09" value="9" alpha="255"/>
        <paletteEntry color="#729a55" label="FBFM10" value="10" alpha="255"/>
        <paletteEntry color="#ebd4fd" label="FBFM11" value="11" alpha="255"/>
        <paletteEntry color="#a3b1f3" label="FBFM12" value="12" alpha="255"/>
        <paletteEntry color="#ba7750" label="Urban" value="91" alpha="255"/>
        <paletteEntry color="#eaeaea" label="Snow/Ice" value="92" alpha="255"/>
        <paletteEntry color="#fdf2f2" label="Agricolture" value="93" alpha="255"/>
        <paletteEntry color="#89b7dd" label="Water" value="98" alpha="255"/>
        <paletteEntry color="#85999c" label="Barren" value="99" alpha="255"/>
      </colorPalette>
      <colorramp name="[source]" type="gradient">
        <prop k="color1" v="215,25,28,255"/>
        <prop k="color2" v="43,131,186,255"/>
        <prop k="discrete" v="0"/>
        <prop k="rampType" v="gradient"/>
        <prop k="stops" v="0.25;253,174,97,255:0.5;255,255,191,255:0.75;171,221,164,255"/>
      </colorramp>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0"/>
    <huesaturation grayscaleMode="0" colorizeStrength="100" saturation="0" colorizeGreen="128" colorizeOn="0" colorizeBlue="128" colorizeRed="255"/>
    <rasterresampler maxOversampling="2" zoomedInResampler="bilinear"/>
  </pipe>
  <blendMode>6</blendMode>
</qgis>
